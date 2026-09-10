from __future__ import annotations

import base64
import fcntl
import json
import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any


class BlenderPipeline:
    def __init__(self, project_root: Path, executable: str | None = None):
        self.project_root = project_root.resolve()
        self.executable = executable or os.environ.get("BLENDER_BIN", "/snap/bin/blender")
        self.runtime = self.project_root / ".runtime" / "blender-assets"
        self.worker = self.project_root / "tools" / "blender_asset_worker.py"
        self.ue_editor = os.environ.get(
            "UE4_EDITOR_CMD", "/home/moresweet/UnrealEngine_4.26/Engine/Binaries/Linux/UE4Editor-Cmd")
        self.carla_project = os.environ.get(
            "CARLA_PROJECT", "/home/moresweet/carla/Unreal/CarlaUE4/CarlaUE4.uproject")
        self.importer = self.project_root / "integration" / "carla" / "import_generated_asset.py"
        self.registry_path = self.runtime / "registry.json"

    def status(self) -> dict[str, Any]:
        try:
            completed = subprocess.run([self.executable, "--version"], capture_output=True,
                                       text=True, timeout=20, check=True)
            version = completed.stdout.splitlines()[0]
            return {"ok": True, "available": True, "executable": self.executable,
                    "version": version, "output_root": str(self.runtime)}
        except (OSError, subprocess.SubprocessError) as exc:
            return {"ok": True, "available": False, "executable": self.executable,
                    "error": str(exc), "output_root": str(self.runtime)}

    def run(self, request: dict[str, Any]) -> dict[str, Any]:
        spec = self._normalize(request)
        job_id = uuid.uuid4().hex[:12]
        output = self.runtime / job_id
        output.mkdir(parents=True, exist_ok=False)
        texture = request.get("texture_base64")
        if texture:
            raw = base64.b64decode(str(texture).split(",", 1)[-1], validate=True)
            if len(raw) > 25 * 1024 * 1024:
                raise ValueError("texture exceeds the 25 MB local limit")
            texture_path = output / "texture.png"
            texture_path.write_bytes(raw)
            spec["texture_path"] = str(texture_path)
        spec_path = output / "request.json"
        spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
        completed = subprocess.run([
            self.executable, "--background", "--factory-startup", "--python", str(self.worker),
            "--", str(spec_path), str(output),
        ], capture_output=True, text=True, timeout=180)
        if completed.returncode:
            raise RuntimeError((completed.stderr or completed.stdout)[-4000:])
        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        manifest.update({"job_id": job_id, "log": completed.stdout[-2000:]})
        return manifest

    def import_to_carla(self, job_id: str, asset_name: str | None = None, *, require_clean_exit=True) -> dict[str, Any]:
        if require_clean_exit is not True:
            raise ValueError('Unreal import registration requires a clean process exit')
        self.runtime.mkdir(parents=True, exist_ok=True)
        with (self.runtime / 'import.lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError('Another asset import is active; wait for its recorded outcome') from exc
            return self._import_to_carla(job_id, asset_name, require_clean_exit=require_clean_exit, import_lock_fd=lock.fileno())

    def _import_to_carla(self, job_id: str, asset_name: str | None = None, *, require_clean_exit=True, import_lock_fd: int) -> dict[str, Any]:
        if not job_id.isascii() or not job_id.isalnum() or len(job_id)>64:
            raise ValueError("invalid Blender job id")
        job = (self.runtime / job_id).resolve()
        if self.runtime.resolve() not in job.parents or not job.is_dir():
            raise ValueError('Blender job is outside the asset workspace or missing')
        from .owned_resources import durable_write
        from .session import observed_process_identity
        attempt_id = uuid.uuid4().hex
        report_path = job / ('import-attempt-' + attempt_id + '.json')
        report = {'schema_version':'carla-asset-import/1','attempt_id':attempt_id,
                  'job_id':job_id,'state':'preparing','started_at':time.time(),
                  'owner':observed_process_identity(os.getpid()),'report_path':str(report_path),
                  'live_world_modified':False,'automatic_rollback':False}
        durable_write(report_path,report,exclusive=True)
        def save(): durable_write(report_path,report)
        try:
            result = self._perform_import(job, asset_name, attempt_id, report, save, import_lock_fd)
            report.update(state='registered',ended_at=time.time(),blueprint_id=result['blueprint_id'])
            save()
            return {**result,'import_report':str(report_path)}
        except BaseException as exc:
            report.update(state='needs_attention',ended_at=time.time(),error=str(exc),
                          note='Any created assets are retained at the recorded destination; no implicit retry or deletion')
            save()
            raise RuntimeError(f'Asset import did not complete; inspect {report_path}: {exc}') from exc

    def _perform_import(self, job, asset_name, attempt_id, report, save, import_lock_fd):
        job_id = job.name
        blender_manifest = json.loads((job / "manifest.json").read_text(encoding="utf-8"))
        fbx = Path(blender_manifest["outputs"]["fbx"]).resolve()
        if job.resolve() not in fbx.parents or not fbx.is_file():
            raise ValueError("Blender job has no FBX output")
        safe_name = "".join(ch if ch.isalnum() else "_" for ch in (
            asset_name or blender_manifest.get("name") or job_id)).strip("_")[:48]
        if not safe_name:
            safe_name = "Generated_" + job_id
        if 'generated.prop.' + safe_name.lower() in self.registry():
            raise ValueError('Generated asset ID already registered; choose a new name')
        result_path = job / ("unreal-import-" + attempt_id + ".json")
        request_path = job / ("unreal-request-" + attempt_id + ".json")
        try:
            blender_request = json.loads((job / "request.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            blender_request = {}
        request_path.write_text(json.dumps({
            "asset_id": safe_name, "fbx_path": str(fbx), "result_path": str(result_path),
            "texture_path": blender_request.get("texture_path"),
            "color": blender_request.get("color", [0.15, 0.55, 0.85, 1.0]),
            "roughness": blender_request.get("roughness", 0.45),
        }, indent=2), encoding="utf-8")
        environment = os.environ.copy()
        environment["CSA_UNREAL_IMPORT_REQUEST"] = str(request_path)
        report.update(state='importing',asset_name=safe_name,
                      import_lock_inherited_by_child=True,
                      destination='/Game/Carla/Static/Generated/'+safe_name,
                      request_path=str(request_path),result_path=str(result_path))
        save()  # Persist target ownership before the external process can write assets.
        completed = subprocess.run([
            self.ue_editor, self.carla_project, "-run=pythonscript",
            f"-script={self.importer}", "-unattended", "-nop4", "-nosplash", "-nullrhi",
            f"-abslog={job / ('unreal-' + attempt_id + '.log')}",
        ], capture_output=True, text=True, timeout=600, env=environment,
           pass_fds=(import_lock_fd,))
        log_path = job / ("unreal-log-" + attempt_id + ".json")
        log_path.write_text(json.dumps({
            "attempt_id": attempt_id, "returncode": completed.returncode,
            "stdout_tail": completed.stdout[-1024*1024:],
            "stderr_tail": completed.stderr[-1024*1024:],
            "stdout_truncated": len(completed.stdout) > 1024*1024,
            "stderr_truncated": len(completed.stderr) > 1024*1024,
        }, indent=2), encoding="utf-8")
        if completed.returncode:
            raise RuntimeError(f'Unreal import failed with exit {completed.returncode}; log: {log_path}')
        if not result_path.is_file():
            raise RuntimeError((completed.stderr or completed.stdout)[-6000:])
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if (not isinstance(result, dict) or result.get('ok') is not True
                or result.get('asset_id') != safe_name
                or result.get('blueprint_id') != 'generated.prop.' + safe_name.lower()
                or not isinstance(result.get('mesh_path'), str)
                or not result['mesh_path'].startswith('/Game/Carla/Static/Generated/' + safe_name + '/')):
            raise RuntimeError(f'Unreal import result identity mismatch; log: {log_path}')
        result.update(import_attempt_id=attempt_id, import_returncode=completed.returncode,
                      import_log=str(log_path))
        registry = self.registry()
        registry[result["blueprint_id"]] = result
        self.runtime.mkdir(parents=True, exist_ok=True)
        temporary = self.registry_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(registry, indent=2), encoding="utf-8")
        temporary.replace(self.registry_path)
        result["log"] = completed.stdout[-3000:]
        return result

    def import_attempts(self):
        reports=[]
        for path in self.runtime.glob('*/import-attempt-*.json'):
            if path.stat().st_size>65536:
                raise ValueError('Oversized asset import report')
            report=json.loads(path.read_text())
            if not isinstance(report,dict) or report.get('schema_version')!='carla-asset-import/1':
                raise ValueError('Invalid asset import report: '+str(path))
            reports.append(report)
        return sorted(reports,key=lambda r:r['started_at'],reverse=True)[:100]

    def registry(self) -> dict[str, dict[str, Any]]:
        try:
            if self.registry_path.stat().st_size > 16*1024*1024:
                raise ValueError('Generated asset registry exceeds size limit')
            registry = json.loads(self.registry_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError('Generated asset registry is unreadable; refusing to replace it') from exc
        if not isinstance(registry, dict) or any(
                not isinstance(key, str) or not key.startswith('generated.prop.') or
                not isinstance(value, dict) or value.get('blueprint_id') != key or
                not isinstance(value.get('mesh_path'), str) or not value['mesh_path'].startswith('/Game/')
                for key, value in registry.items()):
            raise ValueError('Generated asset registry has invalid entries; refusing to replace it')
        return registry

    def _normalize(self, request: dict[str, Any]) -> dict[str, Any]:
        shape = str(request.get("shape", "cube"))
        if shape not in {"cube", "cylinder", "cone", "sphere", "plane"}:
            raise ValueError("shape must be cube, cylinder, cone, sphere or plane")
        dimensions = request.get("dimensions", [2, 2, 2])
        if not isinstance(dimensions, list) or len(dimensions) != 3:
            raise ValueError("dimensions must contain x, y and z")
        spec: dict[str, Any] = {
            "name": str(request.get("name", "GeneratedAsset"))[:63],
            "shape": shape,
            "dimensions": [max(0.01, min(1000.0, float(value))) for value in dimensions],
            "color": request.get("color", [0.15, 0.55, 0.85, 1.0]),
            "roughness": max(0.0, min(1.0, float(request.get("roughness", 0.45)))),
        }
        source = request.get("source_path")
        if source:
            path = Path(str(source)).expanduser().resolve()
            if not path.is_file() or path.suffix.lower() not in {".fbx", ".glb", ".gltf", ".obj", ".blend"}:
                raise ValueError("source_path must be an existing FBX, GLB, GLTF, OBJ or BLEND file")
            spec["source_path"] = str(path)
        return spec

from __future__ import annotations

import base64
import fcntl
import json
import math
import os
import subprocess
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any


class BlenderPipeline:
    @contextmanager
    def operation_admission(self):
        self.runtime.mkdir(parents=True, exist_ok=True)
        with (self.runtime / 'bridge-restart.lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError('Bridge restart in progress; asset operation rejected') from exc
            yield lock.fileno()

    @staticmethod
    def observe_attempt(report):
        """Read-only coordinator observation, never proof that a child has stopped."""
        if report.get('state') not in ('preparing', 'generating', 'importing'):
            return report
        from .session import observed_process_identity
        owner = report.get('owner')
        status = 'unknown'
        error = None
        try:
            if (not isinstance(owner, dict) or set(owner) != {'pid', 'start_ticks'}
                    or not isinstance(owner['start_ticks'], str) or not owner['start_ticks'].isdigit()):
                raise ValueError('Missing or invalid coordinator identity')
            status = 'present' if observed_process_identity(owner['pid']) == owner else 'exited'
        except (OSError, ValueError) as exc:
            error = str(exc)
        return {**report, 'observation': {
            'coordinator': status, 'error': error,
            'requires_attention': status != 'present',
            'child_state': 'unknown', 'automatic_retry_allowed': False,
            'note': 'Coordinator presence does not prove task progress; coordinator exit does not prove Blender/Unreal child exit. Inspect retained outputs before any recovery.'}}

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

    def preview_plan(self, data):
        from .asset_plan import archive_plan
        if not isinstance(data, dict) or set(data) != {'description'}:
            raise ValueError('Expected only an asset description')
        return archive_plan(self.runtime / 'plans', data['description'])

    def execute_plan(self, data):
        from .asset_plan import read_plan
        if not isinstance(data, dict) or set(data) != {'plan_sha256', 'confirmed'} or data['confirmed'] is not True:
            raise ValueError('Confirm exactly one archived asset plan')
        plan = read_plan(self.runtime / 'plans', data['plan_sha256'])
        return self.run(plan['spec'], plan_sha256=data['plan_sha256'])

    def run(self, request: dict[str, Any], *, plan_sha256=None) -> dict[str, Any]:
        spec = self._normalize(request)
        with self.operation_admission() as admission_fd:
            return self._run(request, spec, plan_sha256=plan_sha256, admission_fd=admission_fd)

    def _run(self, request: dict[str, Any], spec, *, plan_sha256=None, admission_fd: int) -> dict[str, Any]:
        from .owned_resources import durable_write
        from .session import observed_process_identity
        raw = None
        texture = request.get("texture_base64")
        if texture:
            if not isinstance(texture, str) or len(texture) > 36 * 1024 * 1024:
                raise ValueError('Texture encoding exceeds the local limit')
            raw = base64.b64decode(texture.split(',', 1)[-1], validate=True)
            if len(raw) > 25 * 1024 * 1024:
                raise ValueError("texture exceeds the 25 MB local limit")
        job_id = uuid.uuid4().hex[:12]
        output = self.runtime / job_id
        output.mkdir(parents=True, exist_ok=False)
        report_path = output / 'generation.json'
        report = {'schema_version': 'carla-asset-generation/1', 'attempt_id': job_id,
                  'job_id': job_id, 'state': 'preparing', 'started_at': time.time(),
                  'owner': observed_process_identity(os.getpid()), 'report_path': str(report_path),
                  'destination': str(output), 'live_world_modified': False,
                  'automatic_retry': False, 'automatic_rollback': False}
        if plan_sha256 is not None:
            report['plan_sha256'] = plan_sha256
        durable_write(report_path, report, exclusive=True)
        try:
            if raw is not None:
                texture_path = output / "texture.png"
                texture_path.write_bytes(raw)
                spec["texture_path"] = str(texture_path)
            spec_path = output / "request.json"
            durable_write(spec_path, spec, exclusive=True)
            report['state'] = 'generating'
            durable_write(report_path, report)
            completed = subprocess.run([
                self.executable, "--background", "--factory-startup", "--python", str(self.worker),
                "--", str(spec_path), str(output),
            ], capture_output=True, text=True, timeout=180, pass_fds=(admission_fd,))
            report.update(returncode=completed.returncode, log=completed.stdout[-2000:])
            if completed.returncode:
                raise RuntimeError((completed.stderr or completed.stdout)[-4000:])
            manifest_path = output / 'manifest.json'
            if manifest_path.stat().st_size > 65536:
                raise ValueError('Oversized Blender result')
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            if not isinstance(manifest, dict) or manifest.get('ok') is not True:
                raise ValueError('Blender did not report a successful export')
            outputs = manifest.get('outputs')
            if not isinstance(outputs, dict):
                raise ValueError('Blender export output inventory is missing')
            for kind in ('blend', 'glb', 'fbx'):
                exported = outputs.get(kind)
                expected = output / ('asset.' + kind)
                if (not isinstance(exported, str) or Path(exported) != expected
                        or expected.is_symlink() or not expected.is_file()
                        or expected.stat().st_size == 0):
                    raise ValueError(f'Blender export is incomplete: missing or invalid {kind} output')
            report.update(state='exported', ended_at=time.time())
            durable_write(report_path, report)
            manifest.update(job_id=job_id, log=completed.stdout[-2000:], generation_report=str(report_path))
            return manifest
        except BaseException as exc:
            report.update(state='needs_attention', ended_at=time.time(), error=str(exc)[-4000:])
            try:
                durable_write(report_path, report)
            except OSError as publication_error:
                raise RuntimeError(f'Generation status could not be saved; inspect {report_path}; {exc}; {publication_error}') from exc
            raise RuntimeError(f'Blender generation did not complete; retained files: {report_path}: {exc}') from exc

    def generation_attempts(self, *, limit=100):
        reports = []
        for path in self.runtime.glob('*/generation.json'):
            if path.is_symlink() or path.parent.is_symlink() or path.stat().st_size > 65536:
                raise ValueError('Invalid generation report path or size')
            report = json.loads(path.read_text())
            if (not isinstance(report, dict) or report.get('schema_version') != 'carla-asset-generation/1'
                    or report.get('job_id') != path.parent.name
                    or report.get('attempt_id') != path.parent.name
                    or report.get('state') not in ('preparing', 'generating', 'exported', 'needs_attention')
                    or type(report.get('started_at')) not in (int, float)
                    or not math.isfinite(report['started_at'])):
                raise ValueError('Invalid generation report: ' + str(path))
            reports.append(self.observe_attempt(report))
        return sorted(reports, key=lambda row: row['started_at'], reverse=True)[:limit]

    def exported_asset(self, job_id):
        """Reopen an explicitly completed export without executing external tools."""
        if not isinstance(job_id, str) or not job_id.isascii() or not job_id.isalnum() or len(job_id)>64:
            raise ValueError('Invalid Blender job id')
        job = self.runtime / job_id
        if job.is_symlink():
            raise ValueError('Linked asset job')
        def read(name):
            path = job / name
            if path.is_symlink() or path.stat().st_size > 65536:
                raise ValueError('Invalid asset metadata')
            value = json.loads(path.read_text())
            if not isinstance(value, dict):
                raise ValueError('Invalid asset metadata')
            return value
        report = read('generation.json')
        if (report.get('schema_version') != 'carla-asset-generation/1'
                or report.get('job_id') != job_id or report.get('attempt_id') != job_id
                or report.get('state') != 'exported'):
            raise ValueError('Only confirmed exports can be reopened')
        manifest = read('manifest.json')
        outputs = manifest.get('outputs')
        if manifest.get('ok') is not True or not isinstance(outputs, dict):
            raise ValueError('Invalid export manifest')
        for kind in ('blend', 'glb', 'fbx'):
            path = job / ('asset.' + kind)
            if outputs.get(kind) != str(path) or path.is_symlink() or not path.is_file() or not path.stat().st_size:
                raise ValueError('Export files are missing or invalid')
        return {**manifest, 'job_id': job_id, 'generation_report': str(job / 'generation.json'),
                'reopened': True}

    def import_to_carla(self, job_id: str, asset_name: str | None = None, *, require_clean_exit=True) -> dict[str, Any]:
        with self.operation_admission():
            return self._admitted_import(job_id, asset_name, require_clean_exit=require_clean_exit)

    def _admitted_import(self, job_id: str, asset_name: str | None = None, *, require_clean_exit=True) -> dict[str, Any]:
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
                  'worker_state':'not_started',
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
            try:
                save()
            except OSError as publication_error:
                raise RuntimeError(f'Import status could not be saved; inspect {report_path}; {exc}; {publication_error}') from exc
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
                      worker_state='launching',
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
        report.update(worker_state='exited', worker_returncode=completed.returncode)
        save()
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
        from .owned_resources import durable_write
        durable_write(self.registry_path, registry)
        result["log"] = completed.stdout[-3000:]
        return result

    def import_attempts(self, *, limit=100):
        reports=[]
        registry_error = None
        try:
            registry = self.registry()
        except ValueError as exc:
            registry, registry_error = {}, str(exc)
        for path in self.runtime.glob('*/import-attempt-*.json'):
            if path.is_symlink() or path.parent.is_symlink() or path.stat().st_size>65536:
                raise ValueError('Invalid asset import report path or size')
            report=json.loads(path.read_text())
            attempt_id = path.stem.removeprefix('import-attempt-')
            if (not isinstance(report,dict) or report.get('schema_version')!='carla-asset-import/1'
                    or len(attempt_id) != 32 or any(ch not in '0123456789abcdef' for ch in attempt_id)
                    or report.get('attempt_id') != attempt_id
                    or report.get('job_id') != path.parent.name
                    or report.get('state') not in ('preparing', 'importing', 'registered', 'needs_attention')
                    or type(report.get('started_at')) not in (int, float)
                    or not math.isfinite(report['started_at'])
                    or report.get('report_path') != str(path)):
                raise ValueError('Invalid asset import report: '+str(path))
            matches = [entry for entry in registry.values()
                       if entry.get('import_attempt_id') == attempt_id]
            registration = 'absent'
            if registry_error:
                registration = 'unknown'
            elif matches:
                name = report.get('asset_name')
                expected = 'generated.prop.' + name.lower() if isinstance(name, str) else None
                registration = 'matching' if (len(matches) == 1 and expected is not None
                    and matches[0].get('blueprint_id') == expected
                    and matches[0].get('import_returncode') == 0
                    and matches[0]['mesh_path'].startswith('/Game/Carla/Static/Generated/' + name + '/')) else 'conflict'
            reports.append({**self.observe_attempt(report), 'registration_observation': {
                'state': registration, 'error': registry_error, 'native_verified': False,
                'automatic_retry_allowed': False}})
        return sorted(reports,key=lambda r:r['started_at'],reverse=True)[:limit]

    def restart_status(self):
        # UI history is truncated; restart safety must inspect every journal.
        generations = self.generation_attempts(limit=None)
        imports = self.import_attempts(limit=None)
        def exited_generation(row):
            # subprocess.run returned before returncode was recorded. This proves
            # worker exit, not successful export or that the asset is repaired.
            return (row['state'] == 'needs_attention'
                    and type(row.get('returncode')) is int
                    and type(row.get('ended_at')) in (int, float)
                    and math.isfinite(row['ended_at'])
                    and row['ended_at'] >= row['started_at'])
        settled_failures = [row for row in generations if exited_generation(row)]
        def settled_import(row):
            from .asset_restart_review import has_review
            if has_review(self.runtime, row['job_id'], row['attempt_id']):
                return True
            ended = row.get('ended_at')
            if (row['state'] != 'needs_attention' or type(ended) not in (int, float)
                    or not math.isfinite(ended) or ended < row['started_at']):
                return False
            if row.get('worker_state') == 'not_started':
                return not any(key in row for key in ('destination', 'request_path', 'result_path', 'worker_returncode'))
            return row.get('worker_state') == 'exited' and type(row.get('worker_returncode')) is int
        settled_imports = [row for row in imports if settled_import(row)]
        reports = ([row for row in generations if not exited_generation(row)]
                   + [row for row in imports if not settled_import(row)])
        return {'schema_version': 'asset-restart/1', 'unresolved': [
            {'job_id': row['job_id'], 'attempt_id': row['attempt_id'], 'state': row['state']}
            for row in reports if row['state'] not in ('exported', 'registered')],
            'settled_generation_failures': [
                {'job_id': row['job_id'], 'state': row['state'], 'returncode': row['returncode']}
                for row in settled_failures],
            'settled_import_failures': [
                {'job_id': row['job_id'], 'attempt_id': row['attempt_id'],
                 'state': row['state'], 'worker_state': row.get('worker_state', 'reviewed_prelaunch_rejection')}
                for row in settled_imports]}

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
        if not isinstance(request, dict):
            raise ValueError('Expected asset request object')
        shape = str(request.get("shape", "cube"))
        if shape not in {"cube", "cylinder", "cone", "sphere", "plane"}:
            raise ValueError("shape must be cube, cylinder, cone, sphere or plane")
        dimensions = request.get("dimensions", [2, 2, 2])
        if not isinstance(dimensions, list) or len(dimensions) != 3:
            raise ValueError("dimensions must contain x, y and z")
        color = request.get('color', [0.15, 0.55, 0.85, 1.0])
        def finite(value):
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError('Asset dimensions and materials must be finite numbers')
            return value
        dimensions = [finite(value) for value in dimensions]
        roughness = finite(request.get('roughness', 0.45))
        if not isinstance(color, list) or len(color) != 4 or any(not 0 <= finite(v) <= 1 for v in color):
            raise ValueError('Material color requires four finite channels in 0..1')
        spec: dict[str, Any] = {
            "name": str(request.get("name", "GeneratedAsset"))[:63],
            "shape": shape,
            "dimensions": [max(0.01, min(1000.0, float(value))) for value in dimensions],
            "color": color,
            "roughness": max(0.0, min(1.0, roughness)),
        }
        source = request.get("source_path")
        if source:
            path = Path(str(source)).expanduser().resolve()
            if not path.is_file() or path.suffix.lower() not in {".fbx", ".glb", ".gltf", ".obj", ".blend"}:
                raise ValueError("source_path must be an existing FBX, GLB, GLTF, OBJ or BLEND file")
            spec["source_path"] = str(path)
        return spec

from __future__ import annotations

import base64
import json
import os
import subprocess
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

    def import_to_carla(self, job_id: str, asset_name: str | None = None) -> dict[str, Any]:
        if not job_id.isalnum():
            raise ValueError("invalid Blender job id")
        job = self.runtime / job_id
        blender_manifest = json.loads((job / "manifest.json").read_text(encoding="utf-8"))
        fbx = Path(blender_manifest["outputs"]["fbx"]).resolve()
        if not fbx.is_file():
            raise ValueError("Blender job has no FBX output")
        safe_name = "".join(ch if ch.isalnum() else "_" for ch in (
            asset_name or blender_manifest.get("name") or job_id)).strip("_")[:48]
        if not safe_name:
            safe_name = "Generated_" + job_id
        result_path = job / "unreal-import.json"
        request_path = job / "unreal-request.json"
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
        completed = subprocess.run([
            self.ue_editor, self.carla_project, "-run=pythonscript",
            f"-script={self.importer}", "-unattended", "-nop4", "-nosplash", "-nullrhi",
        ], capture_output=True, text=True, timeout=600, env=environment)
        if not result_path.is_file():
            raise RuntimeError((completed.stderr or completed.stdout)[-6000:])
        result = json.loads(result_path.read_text(encoding="utf-8"))
        registry = self.registry()
        registry[result["blueprint_id"]] = result
        self.runtime.mkdir(parents=True, exist_ok=True)
        temporary = self.registry_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(registry, indent=2), encoding="utf-8")
        temporary.replace(self.registry_path)
        result["log"] = completed.stdout[-3000:]
        if completed.returncode:
            result["warning"] = (
                "UE4Editor returned a non-zero shutdown code after writing the imported asset")
        return result

    def registry(self) -> dict[str, dict[str, Any]]:
        try:
            return json.loads(self.registry_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

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

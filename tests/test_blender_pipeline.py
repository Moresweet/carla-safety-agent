import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from carla_safety_agent.blender_pipeline import BlenderPipeline


def test_normalize_limits_dimensions_and_material(tmp_path: Path):
    pipeline = BlenderPipeline(tmp_path)
    spec = pipeline._normalize({"name": "Barrier", "shape": "cube",
                                "dimensions": [2, 0.4, 5000], "roughness": 2})
    assert spec["dimensions"] == [2.0, 0.4, 1000.0]
    assert spec["roughness"] == 1.0


def test_normalize_requires_real_supported_source(tmp_path: Path):
    pipeline = BlenderPipeline(tmp_path)
    with pytest.raises(ValueError, match="existing FBX"):
        pipeline._normalize({"source_path": str(tmp_path / "missing.fbx")})


def test_pipeline_builds_argument_list_without_shell(monkeypatch, tmp_path: Path):
    worker = tmp_path / "tools" / "blender_asset_worker.py"
    worker.parent.mkdir()
    worker.write_text("pass")
    pipeline = BlenderPipeline(tmp_path, "/opt/blender")

    def run(command, **kwargs):
        assert command[0] == "/opt/blender"
        assert kwargs.get("shell") is None
        output = Path(command[-1])
        (output / "manifest.json").write_text(json.dumps({"ok": True, "outputs": {}}))
        return SimpleNamespace(returncode=0, stdout="done", stderr="")

    monkeypatch.setattr("subprocess.run", run)
    result = pipeline.run({"shape": "sphere", "dimensions": [1, 1, 1]})
    assert result["ok"]
    assert result["job_id"]


def test_unreal_import_registers_generated_blueprint(monkeypatch, tmp_path: Path):
    pipeline = BlenderPipeline(tmp_path, "/opt/blender")
    pipeline.importer.parent.mkdir(parents=True)
    pipeline.importer.write_text("pass")
    job = pipeline.runtime / "abc123"
    job.mkdir(parents=True)
    fbx = job / "asset.fbx"
    fbx.write_bytes(b"fbx")
    (job / "manifest.json").write_text(json.dumps({
        "name": "Barrier", "outputs": {"fbx": str(fbx)}}))

    def run(command, **kwargs):
        request = json.loads(Path(kwargs["env"]["CSA_UNREAL_IMPORT_REQUEST"]).read_text())
        Path(request["result_path"]).write_text(json.dumps({
            "ok": True, "asset_id": "Barrier", "blueprint_id": "generated.prop.barrier",
            "mesh_path": "/Game/Carla/Static/Generated/Barrier/SM_Barrier"}))
        return SimpleNamespace(returncode=0, stdout="imported", stderr="")

    monkeypatch.setattr("subprocess.run", run)
    result = pipeline.import_to_carla("abc123")
    assert result["blueprint_id"] == "generated.prop.barrier"
    assert pipeline.registry()["generated.prop.barrier"]["mesh_path"].endswith("SM_Barrier")

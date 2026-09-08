import json
from pathlib import Path

from carla_safety_agent.dataset import DatasetRecorder, list_datasets
from carla_safety_agent.models import ActorSpec, EnvironmentSpec, OracleSpec, ScenarioResult, ScenarioSpec


def scenario() -> ScenarioSpec:
    return ScenarioSpec(
        scenario_id="dataset-test", family="lead_vehicle", map_name="Town04", seed=9,
        ego=ActorSpec("ego", "vehicle.tesla.model3", 0, 8.0), adversaries=(),
        environment=EnvironmentSpec(), oracle=OracleSpec(), provenance={"source": "test"})


def test_recorder_writes_portable_manifest_and_state(tmp_path: Path):
    recorder = DatasetRecorder(tmp_path, scenario(), 0.05)
    recorder.record({"frame": 0, "ego": {"control": {"steer": 0.1}}})
    (recorder.root / "frames").mkdir()
    (recorder.root / "frames" / "00000001.png").write_bytes(b"png")
    (recorder.root / "trace.json").write_text("[]")
    result = ScenarioResult("dataset-test", "passed", False, 2.0, 4.0, 0.05, 0.1, ())
    manifest_path = recorder.finalize(result)
    manifest = json.loads(manifest_path.read_text())
    assert manifest["schema_version"] == "carla-safety-dataset/0.1"
    assert manifest["frame_count"] == 1
    assert manifest["sensors"]["rgb"]["samples"] == 1
    assert manifest["checksums"]["state_sha256"]
    assert manifest["checksums"]["trace_sha256"]
    assert list_datasets(tmp_path)[0]["run_id"] == recorder.run_id


def test_recorder_preserves_repeated_scenario_runs(tmp_path: Path):
    first = DatasetRecorder(tmp_path, scenario(), 0.05)
    first.finalize(None)
    second = DatasetRecorder(tmp_path, scenario(), 0.05)
    second.finalize(None)
    assert first.root != second.root
    assert len(list_datasets(tmp_path)) == 2

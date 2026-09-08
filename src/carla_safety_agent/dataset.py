from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

from .models import ScenarioResult, ScenarioSpec


SENSOR_LAYOUT = {
    "rgb": ("frames", "png"),
    "depth": ("depth", "png"),
    "semantic": ("semantic", "png"),
    "lidar": ("lidar", "ply"),
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class DatasetRecorder:
    """Writes one portable dataset run without depending on the CARLA module."""

    def __init__(self, root: Path, scenario: ScenarioSpec, fixed_delta_seconds: float):
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        self.run_id = f"{scenario.scenario_id}-{timestamp}-{uuid.uuid4().hex}"
        self.root = root / self.run_id
        self.root.mkdir(parents=True, exist_ok=False)
        self.scenario = scenario
        self.fixed_delta_seconds = fixed_delta_seconds
        self.started_at = _utc_now()
        self.frame_count = 0
        self._state_path = self.root / "state.jsonl"
        self._stream: TextIO = self._state_path.open("w", encoding="utf-8")
        _atomic_json(self.root / "scenario.json", scenario.to_dict())

    def record(self, payload: dict[str, Any]) -> None:
        self._stream.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
        self.frame_count += 1

    def finalize(self, result: ScenarioResult | None, error: BaseException | None = None) -> Path:
        if not self._stream.closed:
            self._stream.flush()
            self._stream.close()
        scenario_path = self.root / "scenario.json"
        trace_path = self.root / "trace.json"
        sensors = {}
        for name, (folder, extension) in SENSOR_LAYOUT.items():
            directory = self.root / folder
            sensors[name] = {
                "path": folder,
                "format": extension,
                "samples": len(list(directory.glob(f"*.{extension}"))) if directory.is_dir() else 0,
            }
        payload: dict[str, Any] = {
            "schema_version": "carla-safety-dataset/0.1",
            "run_id": self.run_id,
            "scenario_id": self.scenario.scenario_id,
            "status": "error" if error else (result.status if result else "incomplete"),
            "started_at": self.started_at,
            "completed_at": _utc_now(),
            "map": self.scenario.map_name,
            "family": self.scenario.family,
            "seed": self.scenario.seed,
            "fixed_delta_seconds": self.fixed_delta_seconds,
            "frame_count": self.frame_count,
            "files": {"scenario": "scenario.json", "state": "state.jsonl",
                      "trace": "trace.json" if trace_path.is_file() else None},
            "sensors": sensors,
            "provenance": self.scenario.provenance,
            "checksums": {
                "scenario_sha256": _sha256(scenario_path),
                "state_sha256": _sha256(self._state_path),
                "trace_sha256": _sha256(trace_path),
            },
            "result": result.to_dict() if result else None,
            "error": str(error) if error else None,
        }
        manifest = self.root / "manifest.json"
        _atomic_json(manifest, payload)
        return manifest


def list_datasets(root: Path) -> list[dict[str, Any]]:
    datasets: list[dict[str, Any]] = []
    if not root.is_dir():
        return datasets
    for manifest in root.glob("*/manifest.json"):
        try:
            item = json.loads(manifest.read_text(encoding="utf-8"))
            item["manifest_path"] = str(manifest)
            datasets.append(item)
        except (OSError, json.JSONDecodeError):
            continue
    return sorted(datasets, key=lambda item: item.get("completed_at", ""), reverse=True)

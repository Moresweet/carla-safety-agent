from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


COLLISION_KEYS = (
    "collisions_layout",
    "collisions_pedestrian",
    "collisions_vehicle",
)


@dataclass(frozen=True)
class TargetFailure:
    route_id: str
    scenario_name: str
    town_name: str
    status: str
    route_completion: float
    driving_score: float
    collisions: int
    infractions: int
    criticality_score: float
    infraction_counts: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _entries(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def parse_bench2drive_results(path: str | Path) -> list[TargetFailure]:
    """Convert Bench2Drive output into a failure-first campaign ranking.

    Bench2Drive rewards an agent. Our score reverses that perspective: low
    composed score, collisions, infractions and runtime failure make a generated
    scenario more interesting for subsequent minimization and replay.
    """
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    records = payload.get("_checkpoint", {}).get("records", [])
    failures: list[TargetFailure] = []
    for record in records:
        infractions = record.get("infractions") or {}
        counts = {name: len(_entries(items)) for name, items in infractions.items()}
        collision_count = sum(counts.get(name, 0) for name in COLLISION_KEYS)
        infraction_count = sum(counts.values())
        scores = record.get("scores") or {}
        route_score = float(scores.get("score_route", 0.0) or 0.0)
        driving_score = float(scores.get("score_composed", 0.0) or 0.0)
        runtime_failure = str(record.get("status", "Unknown")) != "Completed"
        criticality = (
            max(0.0, 100.0 - driving_score)
            + 35.0 * collision_count
            + 5.0 * max(0, infraction_count - collision_count)
            + (20.0 if runtime_failure else 0.0)
        )
        failures.append(TargetFailure(
            route_id=str(record.get("route_id", "unknown")),
            scenario_name=str(record.get("scenario_name", "unknown")),
            town_name=str(record.get("town_name", "unknown")),
            status=str(record.get("status", "Unknown")),
            route_completion=route_score,
            driving_score=driving_score,
            collisions=collision_count,
            infractions=infraction_count,
            criticality_score=round(criticality, 4),
            infraction_counts=counts,
        ))
    return sorted(failures, key=lambda item: item.criticality_score, reverse=True)


def write_failure_report(source: str | Path, output: str | Path) -> Path:
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "schema_version": "carla-safety-target-report/0.1",
        "target": "uniad",
        "source": str(source),
        "ranked_failures": [item.to_dict() for item in parse_bench2drive_results(source)],
    }
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return output_path

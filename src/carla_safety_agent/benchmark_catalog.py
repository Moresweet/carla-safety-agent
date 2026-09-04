"""Read-only adapters for external driving benchmark assets and reports."""

from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ABILITY_GROUPS = {
    "overtaking": {"Accident", "AccidentTwoWays", "ConstructionObstacle",
                    "ConstructionObstacleTwoWays", "HazardAtSideLane", "ParkedObstacle"},
    "merging": {"EnterActorFlow", "HighwayExit", "HighwayCutIn", "ParkingExit",
                "SequentialLaneChange", "NonSignalizedJunctionLeftTurn"},
    "emergency_brake": {"BlockedIntersection", "DynamicObjectCrossing", "HardBreakRoute",
                        "PedestrianCrossing", "ParkingCutIn", "StaticCutIn", "ControlLoss"},
    "give_way": {"InvadingTurn", "YieldToEmergencyVehicle"},
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def route_catalog(root: Path) -> dict[str, Any]:
    data = root / "leaderboard/data"
    collections = []
    for path in sorted(data.glob("*.xml")):
        try:
            routes = ET.parse(path).getroot().findall("route")
        except (ET.ParseError, OSError):
            continue
        scenarios = Counter(s.get("type", "Unknown") for route in routes
                            for s in route.findall("./scenarios/scenario"))
        towns = Counter(route.get("town", "Unknown") for route in routes)
        entries = []
        for route in routes:
            kinds = [s.get("type", "Unknown") for s in route.findall("./scenarios/scenario")]
            entries.append({"id": route.get("id", ""), "town": route.get("town", "Unknown"),
                            "scenarios": kinds})
        collections.append({"id": path.stem, "name": path.name, "path": str(path),
                            "route_count": len(routes), "towns": dict(towns),
                            "scenario_types": dict(scenarios), "routes": entries,
                            "sha256": _sha256(path)})
    return {"source": "Thinklab-SJTU/Bench2Drive", "mode": "external-read-only",
            "license": "CC BY-NC-ND 4.0", "collections": collections}


def algorithm_catalog(zoo: Path) -> list[dict[str, Any]]:
    definitions = [
        ("uniad-tiny", "UniAD-Tiny", "team_code/uniad_b2d_agent.py",
         "ckpts/uniad_tiny_b2d.pth", "available"),
        ("vad", "VAD", "team_code/vad_b2d_agent.py", "ckpts/vad_b2d.pth", "missing_checkpoint"),
    ]
    result = []
    for identifier, name, agent, checkpoint, fallback in definitions:
        agent_path, checkpoint_path = zoo / agent, zoo / checkpoint
        state = "available" if agent_path.is_file() and checkpoint_path.is_file() else fallback
        result.append({"id": identifier, "name": name, "adapter": str(agent_path),
                       "checkpoint": str(checkpoint_path), "status": state,
                       "source": "Thinklab-SJTU/Bench2DriveZoo"})
    return result


def benchmark_report(zoo: Path) -> dict[str, Any]:
    reports = []
    for path in sorted((zoo / "analysis").glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        records = payload.get("_checkpoint", {}).get("records", [])
        if not records:
            continue
        score_route = [float((r.get("scores") or {}).get("score_route", 0)) for r in records]
        score_drive = [float((r.get("scores") or {}).get("score_composed", 0)) for r in records]
        infractions = Counter()
        abilities: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for record in records:
            values = record.get("infractions") or {}
            for key, items in values.items():
                infractions[key] += len(items) if isinstance(items, list) else int(bool(items))
            scenario = str(record.get("scenario_name", ""))
            clean = str(record.get("status")) in {"Completed", "Perfect"} and not any(
                items for key, items in values.items() if key != "min_speed_infractions")
            for ability, members in ABILITY_GROUPS.items():
                if scenario in members:
                    abilities[ability][1] += 1
                    abilities[ability][0] += int(clean)
        reports.append({"algorithm": path.stem, "routes": len(records),
                        "driving_score": sum(score_drive)/len(score_drive),
                        "route_completion": sum(score_route)/len(score_route),
                        "infractions": dict(infractions),
                        "abilities": {key: {"success": value[0], "total": value[1],
                                            "rate": value[0]/value[1] if value[1] else None}
                                      for key, value in abilities.items()},
                        "source_file": str(path), "sha256": _sha256(path)})
    return {"schema_version": "carla-safety-benchmark-report/0.1",
            "source": "external-published-results", "reports": reports}

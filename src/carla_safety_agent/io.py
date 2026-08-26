from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import ActorSpec, EnvironmentSpec, OracleSpec, ScenarioSpec


def save_specs(specs: list[ScenarioSpec], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([s.to_dict() for s in specs], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def load_specs(path: Path) -> list[ScenarioSpec]:
    raw: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    result = []
    for item in raw:
        item["ego"] = ActorSpec(**item["ego"])
        item["adversaries"] = tuple(ActorSpec(**a) for a in item["adversaries"])
        item["environment"] = EnvironmentSpec(**item["environment"])
        item["oracle"] = OracleSpec(**item["oracle"])
        result.append(ScenarioSpec(**item))
    return result

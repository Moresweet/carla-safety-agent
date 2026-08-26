from __future__ import annotations

from dataclasses import asdict, dataclass

from .models import ScenarioSpec
from .nhtsa import INTERACTION_TYPES


@dataclass(frozen=True)
class BuildPlan:
    schema_version: str
    scenario_id: str
    interaction: str
    map_name: str
    actors: tuple[dict[str, object], ...]
    generated_assets: tuple[dict[str, object], ...]
    generated_map: dict[str, object] | None
    trigger: dict[str, object]
    render: dict[str, object]
    diagnostics: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def build_plan(spec: ScenarioSpec) -> BuildPlan:
    if spec.family not in INTERACTION_TYPES and spec.family != "road_hazard":
        raise ValueError(f"scenario is not in the supported NHTSA subset: {spec.family}")
    if spec.family != "road_hazard" and len(spec.adversaries) != 1:
        raise ValueError("initial renderer requires exactly one principal other actor")
    adversary = spec.adversaries[0] if spec.adversaries else None
    diagnostics: list[str] = []
    if adversary and spec.ego.spawn_index == adversary.spawn_index:
        diagnostics.append("actors_share_spawn_index")
    return BuildPlan(
        schema_version="carla-safety-build-plan/0.1",
        scenario_id=spec.scenario_id,
        interaction=spec.family,
        map_name=spec.map_name,
        actors=(spec.ego.__dict__,) + ((adversary.__dict__,) if adversary else ()),
        generated_assets=tuple(asset.__dict__ for asset in spec.generated_assets),
        generated_map=asdict(spec.generated_map) if spec.generated_map else None,
        trigger={
            "type": "distance",
            "threshold_m": adversary.trigger_distance_m if adversary else None,
            "action": adversary.behavior if adversary else "static_hazard",
        },
        render={"camera": "ego_chase_rgb", "width": 1280, "height": 720, "every_n_frames": 5},
        diagnostics=tuple(diagnostics),
    )

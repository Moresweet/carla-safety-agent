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
    trigger: dict[str, object]
    render: dict[str, object]
    diagnostics: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def build_plan(spec: ScenarioSpec) -> BuildPlan:
    if spec.family not in INTERACTION_TYPES:
        raise ValueError(f"scenario is not in the supported NHTSA subset: {spec.family}")
    if len(spec.adversaries) != 1:
        raise ValueError("initial renderer requires exactly one principal other actor")
    adversary = spec.adversaries[0]
    diagnostics: list[str] = []
    if spec.ego.spawn_index == adversary.spawn_index:
        diagnostics.append("actors_share_spawn_index")
    return BuildPlan(
        schema_version="carla-safety-build-plan/0.1",
        scenario_id=spec.scenario_id,
        interaction=spec.family,
        map_name=spec.map_name,
        actors=(spec.ego.__dict__, adversary.__dict__),
        trigger={
            "type": "distance",
            "threshold_m": adversary.trigger_distance_m,
            "action": adversary.behavior,
        },
        render={"camera": "ego_chase_rgb", "width": 1280, "height": 720, "every_n_frames": 5},
        diagnostics=tuple(diagnostics),
    )

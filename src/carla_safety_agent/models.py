from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Range:
    low: float
    high: float

    def __post_init__(self) -> None:
        if self.low > self.high:
            raise ValueError(f"invalid range: {self.low} > {self.high}")


@dataclass(frozen=True)
class ActorSpec:
    role: str
    blueprint: str
    spawn_index: int
    speed_mps: float
    lateral_offset_m: float = 0.0
    trigger_distance_m: float | None = None
    behavior: str = "autopilot"


@dataclass(frozen=True)
class EnvironmentSpec:
    cloudiness: float = 0.0
    precipitation: float = 0.0
    fog_density: float = 0.0
    sun_altitude_angle: float = 45.0
    friction_scale: float = 1.0


@dataclass(frozen=True)
class OracleSpec:
    collision_is_failure: bool = True
    min_ttc_s: float = 1.5
    min_distance_m: float = 1.0
    max_duration_s: float = 20.0


@dataclass(frozen=True)
class ProceduralAssetSpec:
    asset_id: str
    kind: str
    shape: str
    dimensions_m: tuple[float, float, float]
    mass_kg: float
    distance_ahead_m: float
    lateral_offset_m: float = 0.0
    count: int = 1
    color: str = "rust"

    def __post_init__(self) -> None:
        if any(value <= 0 for value in self.dimensions_m):
            raise ValueError("asset dimensions must be positive")
        if self.mass_kg < 0:
            raise ValueError("asset mass cannot be negative")
        if self.distance_ahead_m <= 0:
            raise ValueError("asset distance must be positive")
        if self.count < 1:
            raise ValueError("asset count must be positive")


@dataclass(frozen=True)
class RoadSegmentSpec:
    kind: str
    length_m: float
    curvature: float = 0.0
    grade: float = 0.0

    def __post_init__(self) -> None:
        if self.kind not in {"line", "arc"}:
            raise ValueError(f"unsupported road segment: {self.kind}")
        if self.length_m <= 0:
            raise ValueError("road segment length must be positive")
        if self.kind == "arc" and self.curvature == 0:
            raise ValueError("arc curvature cannot be zero")
        if abs(self.grade) > 0.15:
            raise ValueError("road grade exceeds the supported 15 percent limit")


@dataclass(frozen=True)
class GeneratedMapSpec:
    name: str
    segments: tuple[RoadSegmentSpec, ...]
    lane_width_m: float = 3.5
    lanes_each_direction: int = 2
    speed_limit_mps: float = 20.0
    realistic_environment: bool = True
    tree_count: int = 20
    building_count: int = 8
    pedestrian_count: int = 6
    traffic_vehicle_count: int = 6

    def __post_init__(self) -> None:
        if not self.segments:
            raise ValueError("generated map requires at least one road segment")
        if self.lane_width_m <= 0 or self.lanes_each_direction < 1:
            raise ValueError("generated map lane geometry is invalid")
        if min(self.tree_count, self.building_count, self.pedestrian_count,
               self.traffic_vehicle_count) < 0:
            raise ValueError("environment actor counts cannot be negative")


@dataclass(frozen=True)
class ScenarioSpec:
    scenario_id: str
    family: str
    map_name: str
    seed: int
    ego: ActorSpec
    adversaries: tuple[ActorSpec, ...]
    environment: EnvironmentSpec
    oracle: OracleSpec
    generated_assets: tuple[ProceduralAssetSpec, ...] = ()
    generated_map: GeneratedMapSpec | None = None
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ScenarioResult:
    scenario_id: str
    status: str
    collision: bool
    min_ttc_s: float | None
    min_distance_m: float
    elapsed_s: float
    risk_score: float
    failure_reasons: tuple[str, ...]
    trace_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

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
        if self.mass_kg <= 0:
            raise ValueError("asset mass must be positive")
        if self.distance_ahead_m <= 0:
            raise ValueError("asset distance must be positive")
        if self.count < 1:
            raise ValueError("asset count must be positive")


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

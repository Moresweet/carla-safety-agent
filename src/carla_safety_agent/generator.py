from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass

from .models import ActorSpec, EnvironmentSpec, OracleSpec, Range, ScenarioSpec


@dataclass(frozen=True)
class GenerationRequest:
    family: str = "cut_in"
    map_name: str = "Town04"
    count: int = 10
    master_seed: int = 7
    ego_speed_mps: Range = Range(8.0, 18.0)
    adversary_speed_mps: Range = Range(4.0, 16.0)
    trigger_distance_m: Range = Range(5.0, 35.0)
    precipitation: Range = Range(0.0, 80.0)
    fog_density: Range = Range(0.0, 40.0)


class ScenarioGenerator:
    """Produces deterministic, boundary-biased scenario families.

    Sampling is deliberately concentrated near range edges and the estimated
    conflict boundary. This is more useful for safety discovery than uniform
    random traffic generation, while remaining fully reproducible.
    """

    SUPPORTED_FAMILIES = {"cut_in", "hard_brake", "occluded_crossing"}

    def generate(self, request: GenerationRequest) -> list[ScenarioSpec]:
        if request.family not in self.SUPPORTED_FAMILIES:
            raise ValueError(f"unsupported family: {request.family}")
        if request.count < 1:
            raise ValueError("count must be positive")
        rng = random.Random(request.master_seed)
        return [self._one(request, rng, index) for index in range(request.count)]

    def _boundary(self, rng: random.Random, value_range: Range) -> float:
        # Beta(0.55, 0.55) oversamples both edges without excluding the centre.
        unit = rng.betavariate(0.55, 0.55)
        return value_range.low + unit * (value_range.high - value_range.low)

    def _one(self, req: GenerationRequest, rng: random.Random, index: int) -> ScenarioSpec:
        seed = rng.randrange(0, 2**31)
        local = random.Random(seed)
        ego_speed = self._boundary(local, req.ego_speed_mps)
        adv_speed = self._boundary(local, req.adversary_speed_mps)
        trigger = self._boundary(local, req.trigger_distance_m)
        scenario_id = self._id(req.family, req.master_seed, index, seed)
        behavior = {
            "cut_in": "cut_in",
            "hard_brake": "hard_brake",
            "occluded_crossing": "cross_road",
        }[req.family]
        adversary_blueprint = (
            "walker.pedestrian.*" if req.family == "occluded_crossing" else "vehicle.*"
        )
        return ScenarioSpec(
            scenario_id=scenario_id,
            family=req.family,
            map_name=req.map_name,
            seed=seed,
            ego=ActorSpec("ego", "vehicle.tesla.model3", 0, ego_speed, behavior="autopilot"),
            adversaries=(
                ActorSpec(
                    "adversary",
                    adversary_blueprint,
                    8 + index,
                    adv_speed,
                    lateral_offset_m=local.uniform(-0.7, 0.7),
                    trigger_distance_m=trigger,
                    behavior=behavior,
                ),
            ),
            environment=EnvironmentSpec(
                cloudiness=local.uniform(0.0, 100.0),
                precipitation=self._boundary(local, req.precipitation),
                fog_density=self._boundary(local, req.fog_density),
                sun_altitude_angle=local.uniform(-5.0, 70.0),
                friction_scale=local.uniform(0.65, 1.0),
            ),
            oracle=OracleSpec(),
            provenance={
                "generator": "boundary-biased-v1",
                "master_seed": req.master_seed,
                "sample_index": index,
            },
        )

    @staticmethod
    def _id(family: str, master_seed: int, index: int, seed: int) -> str:
        raw = f"{family}:{master_seed}:{index}:{seed}".encode()
        return f"{family}-{hashlib.sha256(raw).hexdigest()[:12]}"

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from .models import (
    ActorSpec, EnvironmentSpec, GeneratedMapSpec, OracleSpec,
    ProceduralAssetSpec, RoadSegmentSpec, ScenarioSpec,
)
from .nhtsa import INTERACTION_TYPES


class DescriptionError(ValueError):
    pass


@dataclass(frozen=True)
class Compilation:
    scenario: ScenarioSpec
    warnings: tuple[str, ...]
    extracted: dict[str, object]


class NaturalLanguageCompiler:
    """Deterministic Chinese/English compiler for the initial NHTSA subset.

    It extracts only supported facts and reports defaults. An LLM can later sit
    in front of this contract, but the executable scenario remains explicit.
    """

    KEYWORDS = {
        "road_hazard": (
            "掉落货物", "散落货物", "金属管", "钢管", "路障", "道路障碍物",
            "fallen cargo", "spilled cargo", "metal pipes", "road debris",
        ),
        "rear_end": (
            "追尾", "前车急刹", "前车刹停", "急刹", "紧急制动",
            "rear-end", "rear end", "hard brake", "emergency braking",
        ),
        "lead_vehicle_lane_change": ("前车变道", "前车换道", "lead vehicle lane change"),
        "vulnerable_road_user": ("行人横穿", "行人穿过", "骑行者", "pedestrian", "cyclist", "vru"),
        "crossing_path": ("交叉路径", "路口横穿", "十字路口", "crossing path", "intersection crossing"),
        "merge": ("汇入", "并入", "匝道合流", "merge", "merging"),
    }

    def compile(self, text: str, seed: int = 7) -> Compilation:
        normalized = text.strip().lower()
        if not normalized:
            raise DescriptionError("description is empty")
        interaction = self._interaction(normalized)
        warnings: list[str] = []
        map_name = self._map(normalized) or "Town04"
        if "town" not in normalized:
            warnings.append("map_not_specified: defaulted to Town04")
        speeds = self._speeds(normalized)
        ego_speed = speeds[0] if speeds else 12.0
        adversary_speed = speeds[1] if len(speeds) > 1 else max(2.0, ego_speed * 0.65)
        if not speeds:
            warnings.append("speed_not_specified: ego defaulted to 12 m/s")
        trigger = self._number_before(normalized, ("米触发", "m trigger", "meters trigger")) or 18.0
        if interaction != "road_hazard" and trigger == 18.0 and not any(
            k in normalized for k in ("触发", "trigger")
        ):
            warnings.append("trigger_not_specified: defaulted to 18 m")
        rain = 70.0 if any(k in normalized for k in ("大雨", "暴雨", "heavy rain")) else 30.0 if any(
            k in normalized for k in ("雨", "rain")) else 0.0
        fog = 45.0 if any(k in normalized for k in ("雾", "fog")) else 0.0
        night = any(k in normalized for k in ("夜", "night", "dark"))
        wants_generated_map = any(k in normalized for k in (
            "新地图", "生成地图", "新道路", "s弯", "s curve", "generated map", "custom road",
        ))
        generated_map = self._generated_map(normalized) if wants_generated_map else None
        if generated_map:
            map_name = "GeneratedOpenDrive"
            warnings = [warning for warning in warnings if not warning.startswith("map_not_specified:")]
        generated_assets: tuple[ProceduralAssetSpec, ...] = ()
        adversaries: tuple[ActorSpec, ...]
        if interaction == "road_hazard":
            asset_distance = self._distance(normalized) or 35.0
            pipe_count = int(self._count(normalized) or 6)
            generated_assets = (ProceduralAssetSpec(
                asset_id="fallen-cargo-01",
                kind="fallen_cargo",
                shape="metal_pipes",
                dimensions_m=(2.5, 0.22, 0.22),
                mass_kg=180.0,
                distance_ahead_m=asset_distance,
                count=pipe_count,
            ),)
            adversaries = ()
            if any(cue in normalized for cue in ("遮挡", "混凝土护栏", "concrete barrier", "occluder")):
                generated_assets += (ProceduralAssetSpec(
                    asset_id="roadside-occluder-01",
                    kind="roadside_occluder",
                    shape="concrete_barriers",
                    dimensions_m=(4.0, 0.5, 1.8),
                    mass_kg=0.0,
                    distance_ahead_m=max(12.0, asset_distance - 18.0),
                    lateral_offset_m=3.2,
                    count=3,
                    color="concrete",
                ),)
        else:
            kind = INTERACTION_TYPES[interaction].actor_kind
            adversaries = (ActorSpec(
                "principal_other",
                "walker.pedestrian.*" if kind == "walker" else "vehicle.*",
                8,
                adversary_speed,
                trigger_distance_m=trigger,
                behavior=INTERACTION_TYPES[interaction].behavior,
            ),)
        scenario_id = f"nl-{interaction}-{hashlib.sha256(f'{seed}:{normalized}'.encode()).hexdigest()[:10]}"
        extracted = {
            "interaction": interaction,
            "map_name": map_name,
            "ego_speed_mps": ego_speed,
            "adversary_speed_mps": adversary_speed,
            "trigger_distance_m": trigger,
            "rain": rain,
            "fog": fog,
            "night": night,
        }
        if generated_assets:
            asset = generated_assets[0]
            extracted["generated_asset"] = {
                "shape": asset.shape,
                "count": asset.count,
                "distance_ahead_m": asset.distance_ahead_m,
                "dimensions_m": list(asset.dimensions_m),
                "mass_kg": asset.mass_kg,
            }
        spec = ScenarioSpec(
            scenario_id=scenario_id,
            family=interaction,
            map_name=map_name,
            seed=seed,
            ego=ActorSpec("ego", "vehicle.tesla.model3", 0, ego_speed, behavior="autopilot"),
            adversaries=adversaries,
            environment=EnvironmentSpec(
                cloudiness=max(rain, fog), precipitation=rain, fog_density=fog,
                sun_altitude_angle=-10.0 if night else 45.0,
            ),
            oracle=OracleSpec(),
            generated_assets=generated_assets,
            generated_map=generated_map,
            provenance={
                "source": "natural_language",
                "description": text,
                "compiler": "deterministic-safety-scenario-v2",
                "defaults": list(warnings),
            },
        )
        return Compilation(spec, tuple(warnings), extracted)

    def _interaction(self, text: str) -> str:
        matches = [code for code, keywords in self.KEYWORDS.items() if any(k in text for k in keywords)]
        if not matches:
            raise DescriptionError(
                "no supported interaction found; use rear-end, lead vehicle lane change, "
                "vulnerable road user, crossing path, or merge"
            )
        if len(matches) > 1:
            raise DescriptionError(f"description matches multiple interactions: {', '.join(matches)}")
        return matches[0]

    @staticmethod
    def _distance(text: str) -> float | None:
        match = re.search(r"(?:前方|ahead(?: by| at)?)\s*(\d+(?:\.\d+)?)\s*(?:米|m\b)", text)
        return float(match.group(1)) if match else None

    @staticmethod
    def _count(text: str) -> float | None:
        match = re.search(r"(\d+)\s*(?:根|pipes?)", text)
        return float(match.group(1)) if match else None

    @staticmethod
    def _generated_map(text: str) -> GeneratedMapSpec:
        lanes_match = re.search(r"(?:双向)?\s*(\d+)\s*车道", text)
        total_lanes = int(lanes_match.group(1)) if lanes_match else 4
        lanes_each_direction = max(1, total_lanes // 2)
        downhill = any(cue in text for cue in ("下坡", "downhill", "descending"))
        grade = -0.05 if downhill else 0.0
        if any(cue in text for cue in ("s弯", "s curve")):
            segments = (
                RoadSegmentSpec("line", 40.0, grade=grade),
                RoadSegmentSpec("arc", 50.0, 0.015, grade),
                RoadSegmentSpec("arc", 50.0, -0.015, grade),
                RoadSegmentSpec("line", 60.0, grade=grade),
            )
        else:
            segments = (RoadSegmentSpec("line", 200.0, grade=grade),)
        return GeneratedMapSpec(
            name="SafetyAgentCustomRoad",
            segments=segments,
            lanes_each_direction=lanes_each_direction,
        )

    @staticmethod
    def _map(text: str) -> str | None:
        match = re.search(r"\btown\s*0?([1-9][0-9]?)\b", text, re.IGNORECASE)
        return f"Town{int(match.group(1)):02d}" if match else None

    @staticmethod
    def _speeds(text: str) -> list[float]:
        values: list[float] = []
        pattern = r"(\d+(?:\.\d+)?)\s*(km/h|kph|公里每小时|m/s|米每秒)"
        for raw, unit in re.findall(pattern, text, re.IGNORECASE):
            value = float(raw)
            values.append(value / 3.6 if unit.lower() in {"km/h", "kph", "公里每小时"} else value)
        return values

    @staticmethod
    def _number_before(text: str, suffixes: tuple[str, ...]) -> float | None:
        for suffix in suffixes:
            match = re.search(rf"(\d+(?:\.\d+)?)\s*{re.escape(suffix)}", text)
            if match:
                return float(match.group(1))
        return None

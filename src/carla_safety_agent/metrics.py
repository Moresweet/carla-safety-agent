from __future__ import annotations

import math
from dataclasses import dataclass

from .models import OracleSpec, ScenarioResult


@dataclass(frozen=True)
class KinematicState:
    x: float
    y: float
    vx: float
    vy: float


def distance(a: KinematicState, b: KinematicState) -> float:
    return math.hypot(b.x - a.x, b.y - a.y)


def ttc(ego: KinematicState, other: KinematicState) -> float | None:
    """Constant-velocity 2D time to closest approach.

    Returns None when actors are not closing. This is an online surrogate,
    not a claim of future collision under changing control inputs.
    """
    rx, ry = other.x - ego.x, other.y - ego.y
    rvx, rvy = other.vx - ego.vx, other.vy - ego.vy
    closing = -(rx * rvx + ry * rvy)
    rel_speed_sq = rvx * rvx + rvy * rvy
    if closing <= 0.0 or rel_speed_sq < 1e-9:
        return None
    return closing / rel_speed_sq


def risk_score(collision: bool, min_ttc_s: float | None, min_distance_m: float) -> float:
    collision_term = 1.0 if collision else 0.0
    ttc_term = 0.0 if min_ttc_s is None else 1.0 / max(min_ttc_s, 0.05)
    distance_term = 1.0 / max(min_distance_m, 0.1)
    return round(100.0 * collision_term + 10.0 * ttc_term + distance_term, 6)


def evaluate(
    scenario_id: str,
    oracle: OracleSpec,
    collision: bool,
    min_ttc_s: float | None,
    min_distance_m: float,
    elapsed_s: float,
    trace_path: str | None = None,
) -> ScenarioResult:
    reasons: list[str] = []
    if collision and oracle.collision_is_failure:
        reasons.append("collision")
    if min_ttc_s is not None and min_ttc_s < oracle.min_ttc_s:
        reasons.append("ttc_below_threshold")
    if min_distance_m < oracle.min_distance_m:
        reasons.append("distance_below_threshold")
    return ScenarioResult(
        scenario_id=scenario_id,
        status="critical" if reasons else "passed",
        collision=collision,
        min_ttc_s=min_ttc_s,
        min_distance_m=min_distance_m,
        elapsed_s=elapsed_s,
        risk_score=risk_score(collision, min_ttc_s, min_distance_m),
        failure_reasons=tuple(reasons),
        trace_path=trace_path,
    )

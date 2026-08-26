from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InteractionType:
    code: str
    title: str
    actor_kind: str
    behavior: str
    description: str


# Initial scope follows the five representative ADS scenario groups used by
# NHTSA DOT HS 813 073. Codes are project-stable identifiers, not claims that
# NHTSA assigned these exact software enum names.
INTERACTION_TYPES: dict[str, InteractionType] = {
    "rear_end": InteractionType(
        "rear_end", "Rear-end", "vehicle", "hard_brake",
        "Ego follows a lead vehicle that slows or stops.",
    ),
    "lead_vehicle_lane_change": InteractionType(
        "lead_vehicle_lane_change", "Lead vehicle lane change", "vehicle", "cut_in",
        "A principal vehicle changes lane across or out of ego's path.",
    ),
    "vulnerable_road_user": InteractionType(
        "vulnerable_road_user", "Vulnerable road user", "walker", "cross_road",
        "A pedestrian or other vulnerable road user crosses ego's path.",
    ),
    "crossing_path": InteractionType(
        "crossing_path", "Crossing path", "vehicle", "cross_road",
        "Two moving road users approach a common conflict area.",
    ),
    "merge": InteractionType(
        "merge", "Merge", "vehicle", "cut_in",
        "A principal vehicle enters ego's lane from a merging lane.",
    ),
}

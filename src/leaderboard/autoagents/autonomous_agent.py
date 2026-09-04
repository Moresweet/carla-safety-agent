"""Small CARLA sensor-agent contract used by the native safety executor.

This module intentionally implements only the stable interface required by
sensor-based driving targets. It is not CARLA Leaderboard or Bench2Drive.
"""

from __future__ import annotations

import datetime
import math
from enum import Enum, IntEnum
from typing import Any

import carla

from leaderboard.envs.sensor_interface import SensorInterface


class Track(Enum):
    SENSORS = "SENSORS"
    MAP = "MAP"
    SENSORS_QUALIFIER = "SENSORS_QUALIFIER"
    MAP_QUALIFIER = "MAP_QUALIFIER"


class RoadOption(IntEnum):
    VOID = -1
    LEFT = 1
    RIGHT = 2
    STRAIGHT = 3
    LANEFOLLOW = 4
    CHANGELANELEFT = 5
    CHANGELANERIGHT = 6


class AutonomousAgent:
    def __init__(self, carla_host: str, carla_port: int, debug: bool = False):
        self.track = Track.SENSORS
        self._global_plan = None
        self._global_plan_world_coord = None
        self.sensor_interface = SensorInterface()
        self.wallclock_t0 = None
        client = carla.Client(carla_host, carla_port)
        client.set_timeout(20.0)
        self.hero_actor = next((actor for actor in client.get_world().get_actors()
                                if actor.attributes.get("role_name") == "hero"), None)

    def setup(self, path_to_conf_file: str) -> None:
        pass

    def sensors(self) -> list[dict[str, Any]]:
        return []

    def run_step(self, input_data: dict[str, Any], timestamp: float) -> carla.VehicleControl:
        return carla.VehicleControl()

    def destroy(self) -> None:
        pass

    @staticmethod
    def get_ros_version() -> int:
        return -1

    def set_global_plan(self, global_plan_gps, global_plan_world_coord) -> None:
        if not global_plan_world_coord:
            raise ValueError("A driving target requires a non-empty global plan")
        selected = [0]
        accumulated = 0.0
        previous = global_plan_world_coord[0][0].location
        for index, (transform, _) in enumerate(global_plan_world_coord[1:], 1):
            location = transform.location
            accumulated += math.hypot(location.x-previous.x, location.y-previous.y)
            if accumulated >= 50.0:
                selected.append(index)
                accumulated = 0.0
            previous = location
        if selected[-1] != len(global_plan_world_coord)-1:
            selected.append(len(global_plan_world_coord)-1)
        self._global_plan_world_coord = [global_plan_world_coord[index] for index in selected]
        self._global_plan = [global_plan_gps[index] for index in selected]
        self._plan_gps_HACK = global_plan_gps

    def get_metric_info(self) -> dict[str, Any]:
        actor = self.hero_actor
        if actor is None:
            return {}
        transform = actor.get_transform()
        vector = lambda value: [value.x, value.y, value.z]
        return {"acceleration": vector(actor.get_acceleration()),
                "angular_velocity": vector(actor.get_angular_velocity()),
                "forward_vector": vector(transform.get_forward_vector()),
                "right_vector": vector(transform.get_right_vector()),
                "location": vector(transform.location),
                "rotation": [transform.rotation.roll, transform.rotation.pitch,
                             transform.rotation.yaw],
                "wallclock": datetime.datetime.now().isoformat()}

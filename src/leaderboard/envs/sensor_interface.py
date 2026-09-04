"""Thread-safe frame collector for project-owned CARLA sensor rigs."""

from __future__ import annotations

import threading
from typing import Any


class SensorConfigurationInvalid(RuntimeError):
    pass


class SensorReceivedNoData(RuntimeError):
    pass


class SensorInterface:
    def __init__(self) -> None:
        self._ids: set[str] = set()
        self._frames: dict[int, dict[str, tuple[int, Any]]] = {}
        self._condition = threading.Condition()

    def register_sensor(self, tag: str, sensor_type: str, sensor: Any) -> None:
        del sensor_type, sensor
        if tag in self._ids:
            raise SensorConfigurationInvalid(f"Duplicated sensor tag: {tag}")
        self._ids.add(tag)

    def update_sensor(self, tag: str, data: Any, frame: int) -> None:
        with self._condition:
            self._frames.setdefault(frame, {})[tag] = (frame, data)
            self._condition.notify_all()

    def get_data(self, frame: int, timeout: float = 30.0) -> dict[str, tuple[int, Any]]:
        with self._condition:
            ready = self._condition.wait_for(
                lambda: self._ids.issubset(self._frames.get(frame, {})), timeout=timeout)
            if not ready:
                missing = sorted(self._ids-set(self._frames.get(frame, {})))
                raise SensorReceivedNoData(f"Frame {frame} is missing sensors: {missing}")
            result = self._frames.pop(frame)
            for stale in [value for value in self._frames if value < frame]:
                self._frames.pop(stale, None)
            return result

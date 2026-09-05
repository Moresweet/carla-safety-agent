"""Atomic evidence publishing for closed-loop model executions."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


CAMERA_IDS = ("CAM_FRONT", "CAM_FRONT_LEFT", "CAM_FRONT_RIGHT",
              "CAM_BACK", "CAM_BACK_LEFT", "CAM_BACK_RIGHT")


def publish_driving_telemetry(*, frame: int, tick: dict[str, Any], plan: Any,
                              control: Any, controller: dict[str, Any],
                              model: str) -> None:
    """Publish actual model inputs, predicted trajectory, and applied control."""
    import numpy as np
    from PIL import Image

    root = Path(os.environ.get("CSA_EVALUATION_CONTROL_DIR", ".runtime/evaluation-control")) / "telemetry"
    root.mkdir(parents=True, exist_ok=True)
    for camera_id in CAMERA_IDS:
        image = tick.get("imgs", {}).get(camera_id)
        if image is None:
            continue
        output = root / f"{camera_id}.jpg"
        temporary = output.with_suffix(".tmp.jpg")
        Image.fromarray(np.asarray(image)[:, :, :3][:, :, ::-1]).save(
            temporary, format="JPEG", quality=72)
        temporary.replace(output)

    vector = lambda value: np.asarray(value).astype(float).tolist()
    payload = {
        "schema_version": "carla-safety-model-evidence/0.2",
        "frame": int(frame), "model": model,
        "inputs": {
            "camera_ids": list(CAMERA_IDS), "speed_mps": float(tick["speed"]),
            "gps": vector(tick["gps"]), "acceleration_mps2": vector(tick["acceleration"]),
            "angular_velocity_radps": vector(tick["angular_velocity"]),
            "route_command": int(tick["command_near"]), "synchronized": True,
        },
        "outputs": {
            "trajectory_ego_m": vector(plan),
            "controller": {
                "steer": float(control.steer), "throttle": float(control.throttle),
                "brake": float(control.brake), "desired_speed_mps": float(controller.get("desired_speed", 0.0)),
                "aim_point_ego_m": vector(controller.get("aim", [0.0, 0.0])),
                "route_target_ego_m": vector(controller.get("target", [0.0, 0.0])),
            },
        },
    }
    temporary = root / "latest.tmp"
    temporary.write_text(json.dumps(payload), encoding="utf-8")
    temporary.replace(root / "latest.json")

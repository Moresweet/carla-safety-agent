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
    active_camera_ids = tuple(camera_id for camera_id in CAMERA_IDS
                              if tick.get("imgs", {}).get(camera_id) is not None)
    for camera_id in active_camera_ids:
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
        "frame": int(frame), "model": os.environ.get("CSA_ALGORITHM_LABEL", model),
        "inputs": {
            "camera_ids": list(active_camera_ids), "speed_mps": float(tick["speed"]),
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


def publish_legacy_agent_telemetry(*, frame: int, input_data: dict[str, Any],
                                   tick: dict[str, Any], control: Any,
                                   controller: dict[str, Any], model: str,
                                   camera_ids: tuple[str, ...]) -> None:
    """Normalize TCP/AD-MLP style agent values into the shared evidence schema."""
    import numpy as np

    imu = np.asarray(input_data.get("IMU", (None, np.zeros(7)))[1])
    images = {}
    for camera_id in camera_ids:
        raw = input_data.get(camera_id)
        if raw is not None:
            images[camera_id] = np.asarray(raw[1])[:, :, :3]
    plan = [controller[key] for key in ("wp_1", "wp_2", "wp_3", "wp_4")
            if key in controller]
    normalized = {
        "imgs": images,
        "speed": tick.get("speed", 0.0),
        "gps": tick.get("gps", [0.0, 0.0]),
        "acceleration": tick.get("acceleration", imu[:3] if imu.size >= 3 else np.zeros(3)),
        "angular_velocity": imu[3:6] if imu.size >= 6 else np.zeros(3),
        "command_near": tick.get("next_command", 0),
    }
    publish_driving_telemetry(frame=frame, tick=normalized, plan=plan,
                              control=control, controller=controller, model=model)

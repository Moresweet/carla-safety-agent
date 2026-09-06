#!/usr/bin/env python3
"""Verify six camera streams traverse ROS publishers and subscriptions."""
import json
import sys
import time
from pathlib import Path

import rclpy
from sensor_msgs.msg import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'ros2/carla_safety_visualization'))
from carla_safety_visualization.bridge import CarlaSafetyBridge

rclpy.init()
node = None
try:
    node = CarlaSafetyBridge()
    received = {name: 0 for name in node.SURROUND_CAMERAS}
    def callback(name):
        def handle(message):
            if message.width and message.height and len(message.data):
                received[name] += 1
        return handle
    subscribers = [node.create_subscription(Image, f'/carla/ego/camera/{name}/image',
                                            callback(name), 10) for name in received]
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and not all(received.values()):
        rclpy.spin_once(node, timeout_sec=0.5)
    output = ROOT/'runs/docker-smoke'
    output.mkdir(parents=True, exist_ok=True)
    report = {'received_images': received, 'all_six_streams_received': all(received.values())}
    (output/'ros-report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))
    assert all(received.values()), 'One or more ROS camera streams produced no images'
finally:
    if node:
        node.destroy_node()
    rclpy.shutdown()

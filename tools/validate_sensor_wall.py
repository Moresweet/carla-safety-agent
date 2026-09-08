"""Bounded real ROS publisher/subscriber + offscreen Qt rendering smoke test."""
import os
import time
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import rclpy
from rclpy.executors import SingleThreadedExecutor
from python_qt_binding.QtCore import QObject
from python_qt_binding.QtWidgets import QApplication
from carla_safety_visualization.capture_relay import CaptureRelay
from carla_safety_visualization.sensor_wall import SensorWall

root = Path(__file__).resolve().parents[1]
rclpy.init(args=['--ros-args', '-p', f'capture_dir:={root}/.runtime/evaluation-control/capture'])
app = QApplication([])

class Context(QObject):
    def __init__(self):
        super().__init__()
        self.node = rclpy.create_node('sensor_wall_validation')
    def add_widget(self, widget):
        widget.show()

context = Context()
wall = SensorWall(context)
relay = CaptureRelay()
executor = SingleThreadedExecutor()
executor.add_node(context.node)
executor.add_node(relay)
try:
    deadline = time.monotonic()+30
    while time.monotonic() < deadline:
        executor.spin_once(timeout_sec=0.02)
        app.processEvents()
        if all(tile.image is not None for tile in wall.tiles.values()):
            break
    missing = [name for name, tile in wall.tiles.items() if tile.image is None]
    assert not missing, f'Missing ROS views: {missing}'
    path = root/'runs/validation/sensor-wall-20260907.png'
    path.parent.mkdir(parents=True, exist_ok=True)
    assert wall.widget.grab().save(str(path))
    print(f'PASS: nine live ROS views rendered to {path}')
finally:
    wall.shutdown_plugin()
    executor.shutdown()
    relay.destroy_node()
    context.node.destroy_node()
    rclpy.shutdown()

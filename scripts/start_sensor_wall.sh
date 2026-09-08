#!/usr/bin/env bash
# Launch from any directory; uses evaluator-owned sensors, never spawns a rig.
set -eo pipefail
SENSOR_PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "${ROS_SETUP:-/opt/ros/lyrical/setup.bash}"
if [[ ! -f "$SENSOR_PROJECT/.runtime/ros-install/setup.bash" ]]; then
  echo 'Build the ROS package first; see docs/sensor-workbench-20260907.md' >&2
  exit 1
fi
source "$SENSOR_PROJECT/.runtime/ros-install/setup.bash"
export ROS_AUTOMATIC_DISCOVERY_RANGE="${ROS_AUTOMATIC_DISCOVERY_RANGE:-LOCALHOST}"
ros2 run carla_safety_visualization capture_relay --ros-args \
  -p "capture_dir:=$SENSOR_PROJECT/.runtime/evaluation-control/capture" &
SENSOR_RELAY_PID=$!
trap 'kill "$SENSOR_RELAY_PID" 2>/dev/null || true' EXIT
rqt --standalone carla_safety_visualization.sensor_wall.SensorWall

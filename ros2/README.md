# ROS2 visualization

`carla_safety_visualization` is an optional ROS2 Python package. It discovers the
CARLA actor whose `role_name` is `hero`, attaches six-direction surround RGB,
depth, semantic and LiDAR
sensors, and publishes those streams together with odometry and TF.

Required runtime packages are `rclpy`, `sensor_msgs`, `nav_msgs`,
`geometry_msgs`, `tf2_ros`, and `rviz2`. Build with `colcon build` from a ROS2
workspace. Ensure the CARLA Python API used by the simulator is also present in
that environment.

The six-camera baseline uses front, front-left, front-right, rear, rear-left and
rear-right cameras with overlapping 90-degree horizontal fields of view. Every
camera publishes `image`, `camera_info`, a physical link frame and a REP-103
optical frame. Extrinsics are centralized in `SURROUND_CAMERAS` for calibration
experiments rather than being presented as a universal industry standard.

This package was runtime-tested with ROS 2 Lyrical. The bridge publishes static
camera and LiDAR extrinsics beneath `ego_vehicle`; image publishers use reliable
QoS for RViz compatibility, while LiDAR uses the sensor-data QoS profile.

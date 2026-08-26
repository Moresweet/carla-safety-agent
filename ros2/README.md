# ROS2 visualization

`carla_safety_visualization` is an optional ROS2 Python package. It discovers the
CARLA actor whose `role_name` is `hero`, attaches RGB, depth, semantic and LiDAR
sensors, and publishes those streams together with odometry and TF.

Required runtime packages are `rclpy`, `sensor_msgs`, `nav_msgs`,
`geometry_msgs`, `tf2_ros`, and `rviz2`. Build with `colcon build` from a ROS2
workspace. Ensure the CARLA Python API used by the simulator is also present in
that environment.

The supplied RViz configuration displays the point cloud, RGB image, semantic
image, odometry and TF tree. Depth remains available as a topic for inspection
or downstream perception nodes.

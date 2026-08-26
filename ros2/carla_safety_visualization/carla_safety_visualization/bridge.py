from __future__ import annotations

import math
import struct

import carla
import rclpy
from geometry_msgs.msg import TransformStamped
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image, PointCloud2, PointField
from tf2_ros import TransformBroadcaster


class CarlaSafetyBridge(Node):
    def __init__(self) -> None:
        super().__init__("carla_safety_visualization")
        self.declare_parameter("host", "127.0.0.1")
        self.declare_parameter("port", 2000)
        self.client = carla.Client(
            self.get_parameter("host").value, self.get_parameter("port").value
        )
        self.client.set_timeout(10.0)
        self.world = self.client.get_world()
        heroes = self.world.get_actors().filter("vehicle.*")
        self.ego = next(
            (actor for actor in heroes if actor.attributes.get("role_name") == "hero"),
            heroes[0] if heroes else None,
        )
        if self.ego is None:
            raise RuntimeError("no CARLA ego vehicle is available")
        self.odom = self.create_publisher(Odometry, "/carla/ego/odometry", 10)
        self.tf = TransformBroadcaster(self)
        self.image_publishers = {
            "rgb": self.create_publisher(Image, "/carla/ego/rgb/image", qos_profile_sensor_data),
            "depth": self.create_publisher(Image, "/carla/ego/depth/image", qos_profile_sensor_data),
            "semantic": self.create_publisher(Image, "/carla/ego/semantic/image", qos_profile_sensor_data),
        }
        self.cloud = self.create_publisher(
            PointCloud2, "/carla/ego/lidar/points", qos_profile_sensor_data
        )
        self.sensors = []
        self._spawn_sensors()
        self.create_timer(0.05, self._publish_pose)
        self.get_logger().info("Publishing RGB, depth, semantic, LiDAR, odometry and TF")

    def _spawn_sensors(self) -> None:
        library = self.world.get_blueprint_library()
        camera_transform = carla.Transform(carla.Location(x=1.5, z=2.0))
        for kind, blueprint_id in (
            ("rgb", "sensor.camera.rgb"),
            ("depth", "sensor.camera.depth"),
            ("semantic", "sensor.camera.semantic_segmentation"),
        ):
            blueprint = library.find(blueprint_id)
            blueprint.set_attribute("image_size_x", "960")
            blueprint.set_attribute("image_size_y", "540")
            sensor = self.world.spawn_actor(blueprint, camera_transform, attach_to=self.ego)
            sensor.listen(lambda image, label=kind: self._publish_image(label, image))
            self.sensors.append(sensor)
        lidar_blueprint = library.find("sensor.lidar.ray_cast")
        lidar_blueprint.set_attribute("range", "80")
        lidar_blueprint.set_attribute("channels", "32")
        lidar_blueprint.set_attribute("points_per_second", "240000")
        lidar = self.world.spawn_actor(
            lidar_blueprint, carla.Transform(carla.Location(z=2.4)), attach_to=self.ego
        )
        lidar.listen(self._publish_cloud)
        self.sensors.append(lidar)

    def _publish_image(self, label: str, image: carla.Image) -> None:
        message = Image()
        message.header.stamp = self.get_clock().now().to_msg()
        message.header.frame_id = "ego_camera"
        message.height, message.width = image.height, image.width
        message.encoding = "bgra8"
        message.is_bigendian = False
        message.step = image.width * 4
        message.data = bytes(image.raw_data)
        self.image_publishers[label].publish(message)

    def _publish_cloud(self, cloud: carla.LidarMeasurement) -> None:
        message = PointCloud2()
        message.header.stamp = self.get_clock().now().to_msg()
        message.header.frame_id = "ego_lidar"
        message.height = 1
        message.width = len(cloud)
        message.fields = [
            PointField(name=name, offset=offset, datatype=PointField.FLOAT32, count=1)
            for name, offset in (("x", 0), ("y", 4), ("z", 8), ("intensity", 12))
        ]
        message.is_bigendian = False
        message.point_step = 16
        message.row_step = message.point_step * message.width
        message.is_dense = True
        message.data = b"".join(
            struct.pack("ffff", point.point.x, -point.point.y, point.point.z, point.intensity)
            for point in cloud
        )
        self.cloud.publish(message)

    def _publish_pose(self) -> None:
        transform, velocity = self.ego.get_transform(), self.ego.get_velocity()
        stamp = self.get_clock().now().to_msg()
        yaw = -math.radians(transform.rotation.yaw)
        qz, qw = math.sin(yaw / 2.0), math.cos(yaw / 2.0)
        odometry = Odometry()
        odometry.header.stamp = stamp
        odometry.header.frame_id = "map"
        odometry.child_frame_id = "ego_vehicle"
        odometry.pose.pose.position.x = transform.location.x
        odometry.pose.pose.position.y = -transform.location.y
        odometry.pose.pose.position.z = transform.location.z
        odometry.pose.pose.orientation.z, odometry.pose.pose.orientation.w = qz, qw
        odometry.twist.twist.linear.x = velocity.x
        odometry.twist.twist.linear.y = -velocity.y
        odometry.twist.twist.linear.z = velocity.z
        self.odom.publish(odometry)
        tf = TransformStamped()
        tf.header, tf.child_frame_id = odometry.header, odometry.child_frame_id
        tf.transform.translation.x = odometry.pose.pose.position.x
        tf.transform.translation.y = odometry.pose.pose.position.y
        tf.transform.translation.z = odometry.pose.pose.position.z
        tf.transform.rotation = odometry.pose.pose.orientation
        self.tf.sendTransform(tf)

    def destroy_node(self) -> bool:
        for sensor in self.sensors:
            sensor.stop()
            sensor.destroy()
        return super().destroy_node()


def main() -> None:
    rclpy.init()
    node = CarlaSafetyBridge()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()

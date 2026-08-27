from __future__ import annotations

import math
import struct

import carla
import rclpy
from geometry_msgs.msg import Point, TransformStamped
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, qos_profile_sensor_data
from sensor_msgs.msg import CameraInfo, Image, PointCloud2, PointField
from tf2_ros import StaticTransformBroadcaster, TransformBroadcaster
from visualization_msgs.msg import Marker, MarkerArray


class CarlaSafetyBridge(Node):
    SURROUND_CAMERAS = {
        "front": (2.0, 0.0, 1.65, 0.0, 90.0),
        "front_left": (1.55, -0.65, 1.60, -60.0, 90.0),
        "front_right": (1.55, 0.65, 1.60, 60.0, 90.0),
        "rear": (-1.75, 0.0, 1.50, 180.0, 90.0),
        "rear_left": (-1.30, -0.68, 1.52, -120.0, 90.0),
        "rear_right": (-1.30, 0.68, 1.52, 120.0, 90.0),
    }

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
        self.static_tf = StaticTransformBroadcaster(self)
        self.image_publishers = {
            "rgb": self.create_publisher(Image, "/carla/ego/rgb/image", 10),
            "depth": self.create_publisher(Image, "/carla/ego/depth/image", 10),
            "semantic": self.create_publisher(Image, "/carla/ego/semantic/image", 10),
        }
        self.surround_publishers = {
            name: self.create_publisher(
                Image, f"/carla/ego/camera/{name}/image", 10
            ) for name in self.SURROUND_CAMERAS
        }
        self.camera_info_publishers = {
            name: self.create_publisher(
                CameraInfo, f"/carla/ego/camera/{name}/camera_info", 10
            ) for name in self.SURROUND_CAMERAS
        }
        self.cloud = self.create_publisher(
            PointCloud2, "/carla/ego/lidar/points", qos_profile_sensor_data
        )
        map_qos = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.road_markers = self.create_publisher(
            MarkerArray, "/carla/map/road_markers", map_qos
        )
        self.sensors = []
        self._spawn_sensors()
        self._publish_sensor_transforms()
        self._publish_road_map()
        self.create_timer(0.05, self._publish_pose)
        self.get_logger().info(
            "Publishing six surround cameras, RGB, depth, semantic, LiDAR, odometry and TF"
        )

    def _publish_road_map(self) -> None:
        marker = Marker()
        marker.header.stamp = self.get_clock().now().to_msg()
        marker.header.frame_id = "map"
        marker.ns = "carla_lane_centerlines"
        marker.id = 0
        marker.type = Marker.LINE_LIST
        marker.action = Marker.ADD
        marker.pose.orientation.w = 1.0
        marker.scale.x = 0.12
        marker.color.r, marker.color.g, marker.color.b, marker.color.a = 0.18, 0.72, 0.95, 0.9
        for waypoint in self.world.get_map().generate_waypoints(3.0):
            following = waypoint.next(3.0)
            if not following:
                continue
            end = following[0]
            if end.road_id != waypoint.road_id or end.lane_id != waypoint.lane_id:
                continue
            for location in (waypoint.transform.location, end.transform.location):
                point = Point()
                point.x, point.y, point.z = location.x, -location.y, location.z + 0.12
                marker.points.append(point)
        self.road_markers.publish(MarkerArray(markers=[marker]))

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
        for name, (x, y, z, yaw, fov) in self.SURROUND_CAMERAS.items():
            blueprint = library.find("sensor.camera.rgb")
            blueprint.set_attribute("image_size_x", "960")
            blueprint.set_attribute("image_size_y", "540")
            blueprint.set_attribute("fov", str(fov))
            transform = carla.Transform(
                carla.Location(x=x, y=y, z=z), carla.Rotation(yaw=yaw)
            )
            sensor = self.world.spawn_actor(blueprint, transform, attach_to=self.ego)
            sensor.listen(lambda image, camera=name: self._publish_surround(camera, image))
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

    def _publish_sensor_transforms(self) -> None:
        stamp = self.get_clock().now().to_msg()
        transforms = []
        for child, x, z in (("ego_camera", 1.5, 2.0), ("ego_lidar", 0.0, 2.4)):
            transform = TransformStamped()
            transform.header.stamp = stamp
            transform.header.frame_id = "ego_vehicle"
            transform.child_frame_id = child
            transform.transform.translation.x = x
            transform.transform.translation.z = z
            transform.transform.rotation.w = 1.0
            transforms.append(transform)
        for name, (x, carla_y, z, yaw_deg, _) in self.SURROUND_CAMERAS.items():
            camera_link = TransformStamped()
            camera_link.header.stamp = stamp
            camera_link.header.frame_id = "ego_vehicle"
            camera_link.child_frame_id = f"camera_{name}_link"
            camera_link.transform.translation.x = x
            camera_link.transform.translation.y = -carla_y
            camera_link.transform.translation.z = z
            yaw = -math.radians(yaw_deg)
            camera_link.transform.rotation.z = math.sin(yaw / 2.0)
            camera_link.transform.rotation.w = math.cos(yaw / 2.0)
            transforms.append(camera_link)
            optical = TransformStamped()
            optical.header.stamp = stamp
            optical.header.frame_id = camera_link.child_frame_id
            optical.child_frame_id = f"camera_{name}_optical"
            optical.transform.rotation.x = -0.5
            optical.transform.rotation.y = 0.5
            optical.transform.rotation.z = -0.5
            optical.transform.rotation.w = 0.5
            transforms.append(optical)
        self.static_tf.sendTransform(transforms)

    def _publish_image(self, label: str, image: carla.Image) -> None:
        if not rclpy.ok():
            return
        message = Image()
        message.header.stamp = self.get_clock().now().to_msg()
        message.header.frame_id = "ego_camera"
        message.height, message.width = image.height, image.width
        message.encoding = "bgra8"
        message.is_bigendian = False
        message.step = image.width * 4
        message.data = bytes(image.raw_data)
        self.image_publishers[label].publish(message)

    def _publish_surround(self, name: str, image: carla.Image) -> None:
        if not rclpy.ok():
            return
        stamp = self.get_clock().now().to_msg()
        frame = f"camera_{name}_optical"
        message = Image()
        message.header.stamp = stamp
        message.header.frame_id = frame
        message.height, message.width = image.height, image.width
        message.encoding = "bgra8"
        message.is_bigendian = False
        message.step = image.width * 4
        message.data = bytes(image.raw_data)
        self.surround_publishers[name].publish(message)
        _, _, _, _, fov_deg = self.SURROUND_CAMERAS[name]
        focal = image.width / (2.0 * math.tan(math.radians(fov_deg) / 2.0))
        info = CameraInfo()
        info.header = message.header
        info.height, info.width = image.height, image.width
        info.distortion_model = "plumb_bob"
        info.k = [focal, 0.0, image.width / 2.0, 0.0, focal, image.height / 2.0, 0.0, 0.0, 1.0]
        info.p = [focal, 0.0, image.width / 2.0, 0.0, 0.0, focal,
                  image.height / 2.0, 0.0, 0.0, 0.0, 1.0, 0.0]
        self.camera_info_publishers[name].publish(info)

    def _publish_cloud(self, cloud: carla.LidarMeasurement) -> None:
        if not rclpy.ok():
            return
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
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

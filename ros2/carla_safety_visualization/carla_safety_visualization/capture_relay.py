"""Publish evaluator-owned capture to ROS without connecting to CARLA.

Images are display JPEG previews; training data remains in lossless datasets.
"""
import io
import json
import math
import time
from pathlib import Path
import numpy as np
from PIL import Image as PILImage
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image, CameraInfo, PointCloud2, PointField

NAMES = {'CAM_FRONT': 'front', 'CAM_FRONT_LEFT': 'front_left', 'CAM_FRONT_RIGHT': 'front_right',
         'CAM_BACK': 'rear', 'CAM_BACK_LEFT': 'rear_left', 'CAM_BACK_RIGHT': 'rear_right'}


class CaptureRelay(Node):
    def __init__(self):
        super().__init__('carla_capture_relay')
        self.declare_parameter('capture_dir', '')
        self.root = Path(self.get_parameter('capture_dir').value)
        if not self.get_parameter('capture_dir').value:
            raise ValueError('Set capture_dir to the project .runtime/evaluation-control/capture directory')
        self.last = None
        self.cameras = {name: self.create_publisher(Image, '/carla/ego/camera/'+tag+'/image', qos_profile_sensor_data) for name, tag in NAMES.items()}
        self.infos = {name: self.create_publisher(CameraInfo, '/carla/ego/camera/'+tag+'/camera_info', qos_profile_sensor_data) for name, tag in NAMES.items()}
        self.depths = {name: self.create_publisher(Image, '/carla/ego/depth/'+tag+'/image', qos_profile_sensor_data) for name, tag in NAMES.items()}
        self.depth = self.create_publisher(Image, '/carla/ego/depth/image', qos_profile_sensor_data)
        self.bev = self.create_publisher(Image, '/carla/ego/bev/image', qos_profile_sensor_data)
        self.cloud = self.create_publisher(PointCloud2, '/carla/ego/lidar/points', qos_profile_sensor_data)
        self.create_timer(.1, self.publish_frame)

    def image_message(self, array, timestamp, name, depth=False):
        message = Image()
        message.header.stamp.sec = int(timestamp)
        message.header.stamp.nanosec = int((timestamp-int(timestamp))*1e9)
        message.header.frame_id = name
        message.height, message.width = array.shape[:2]
        message.encoding = '32FC1' if depth else 'rgb8'
        a = np.ascontiguousarray(array, dtype='<f4' if depth else 'uint8')
        message.step = message.width*(4 if depth else 3)
        message.data = a.tobytes()
        return message

    def publish_frame(self):
        try:
            meta = json.loads((self.root/'latest.json').read_text())
            if meta.get('frame') == self.last or time.time()-meta.get('updated_at', 0) > 5:
                return
            folder = (self.root/meta.get('generation', '.')).resolve()
            if not folder.is_relative_to(self.root.resolve()):
                raise ValueError('Invalid capture generation')
            specs = json.loads((self.root/'calibration.json').read_text())
            timestamp = float(meta['timestamp'])
            for name, publisher in self.cameras.items():
                if name not in meta['available']: continue
                a = np.asarray(PILImage.open(io.BytesIO((folder/(name+'.jpg')).read_bytes())).convert('RGB'))
                image = self.image_message(a, timestamp, 'camera_'+NAMES[name]+'_optical')
                publisher.publish(image)
                info = CameraInfo(); info.header = image.header
                info.width, info.height = image.width, image.height
                focal = image.width/(2*math.tan(math.radians(specs[name]['fov'])/2))
                info.k = [focal,0.,image.width/2,0.,focal,image.height/2,0.,0.,1.]
                info.p = [focal,0.,image.width/2,0.,0.,focal,image.height/2,0.,0.,0.,1.,0.]
                info.distortion_model = 'plumb_bob'
                self.infos[name].publish(info)
                if 'DEPTH_'+name in meta['available']:
                    d = np.load(folder/('DEPTH_'+name+'.npy'), allow_pickle=False)
                    depth = self.image_message(d, timestamp, image.header.frame_id, depth=True)
                    self.depths[name].publish(depth)
                    if name == 'CAM_FRONT': self.depth.publish(depth)
            if 'BEV_RGB' in meta['available']:
                a = np.asarray(PILImage.open(io.BytesIO((folder/'BEV_RGB.jpg').read_bytes())).convert('RGB'))
                self.bev.publish(self.image_message(a, timestamp, 'bev_optical'))
            if 'LIDAR' in meta['available']:
                cloud = np.load(folder/'LIDAR.npy', allow_pickle=False).astype('<f4')
                cloud[:,1] *= -1
                message = PointCloud2(); message.header = self.image_message(np.zeros((1,1,3)), timestamp, 'ego_lidar').header
                message.height = 1; message.width = len(cloud)
                message.fields = [PointField(name=n, offset=i*4, datatype=PointField.FLOAT32, count=1) for i,n in enumerate(('x','y','z','intensity'))]
                message.point_step = 16; message.row_step = 16*len(cloud); message.is_dense = bool(np.isfinite(cloud).all())
                message.data = cloud.tobytes(); self.cloud.publish(message)
            self.last = meta['frame']
        except (OSError, ValueError, KeyError):
            # A generation may have expired; wait for the next complete snapshot.
            return


def main():
    rclpy.init()
    node = CaptureRelay()
    try: rclpy.spin(node)
    except KeyboardInterrupt: pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__': main()

"""rqt sensor wall: six directional cameras, metric depth, top-down point cloud."""
import threading
import time
import numpy as np
from python_qt_binding.QtCore import Qt, QTimer
from python_qt_binding.QtGui import QColor, QImage, QPainter
from python_qt_binding.QtWidgets import QWidget, QVBoxLayout, QGridLayout, QLabel, QDialog
from rqt_gui_py.plugin import Plugin
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image, PointCloud2


def rgb_message(message):
    dtype = np.dtype('>f4' if message.is_bigendian else '<f4')
    if message.encoding == '32FC1':
        depth = np.ndarray((message.height, message.width), dtype=dtype, buffer=bytes(message.data), strides=(message.step, 4))
        v = np.clip(np.log1p(np.nan_to_num(depth, nan=80, posinf=80))/np.log(81), 0, 1)
        return np.stack((255*(1-v), 210*(1-abs(v*2-1)), 255*v), -1).astype('uint8')
    channels = {'rgb8': 3, 'bgr8': 3, 'rgba8': 4, 'bgra8': 4, 'mono8': 1}.get(message.encoding)
    if channels is None:
        raise ValueError('Unsupported encoding '+message.encoding)
    a = np.ndarray((message.height, message.width, channels), dtype=np.uint8,
                   buffer=bytes(message.data), strides=(message.step, channels, 1))
    if channels == 1: return np.repeat(a, 3, axis=2)
    return np.ascontiguousarray(a[:, :, :3][:, :, ::-1] if message.encoding.startswith('bgr') else a[:, :, :3])


def cloud_bev(message):
    offsets = {f.name: f.offset for f in message.fields if f.datatype == 7}
    if not all(n in offsets for n in ('x', 'y', 'z')):
        raise ValueError('PointCloud2 needs float32 x/y/z')
    dtype = np.dtype({'names': ['x', 'y', 'z'], 'formats': [('>f4' if message.is_bigendian else '<f4')]*3,
                      'offsets': [offsets[n] for n in ('x', 'y', 'z')], 'itemsize': message.point_step})
    cloud = np.ndarray((message.height, message.width), dtype=dtype, buffer=bytes(message.data),
                       strides=(message.row_step, message.point_step)).reshape(-1)
    x, y, z = cloud['x'], cloud['y'], cloud['z']
    valid = np.isfinite(x)&np.isfinite(y)&np.isfinite(z)&(abs(x)<60)&(abs(y)<60)
    x, y, z = x[valid], y[valid], z[valid]
    result = np.full((600, 600, 3), (8, 18, 28), dtype=np.uint8)
    result[::50, :] = (28, 46, 62); result[:, ::50] = (28, 46, 62)
    # ROS x-forward/y-left; front is up, left is left.
    col, row = (300-y*5).astype(int), (300-x*5).astype(int)
    h = np.clip((z+3)/8, 0, 1)
    result[row, col] = np.stack((50+180*h, 230-80*h, 210-150*h), axis=-1).astype('uint8')
    result[294:306, 297:303] = 255
    return result


class ImageTile(QWidget):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.title, self.image, self.updated = title, None, 0
        self.setMinimumSize(220, 155)
    def set_image(self, data):
        a = np.ascontiguousarray(data)
        self.image = QImage(a.data, a.shape[1], a.shape[0], a.strides[0], QImage.Format.Format_RGB888).copy()
        self.updated = time.monotonic()
        self.update()
    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor('#0a1520'))
        if self.image is not None:
            target = self.rect().adjusted(4, 4, -4, -30)
            size = self.image.size().scaled(target.size(), Qt.AspectRatioMode.KeepAspectRatio)
            target.setSize(size); target.moveCenter(self.rect().adjusted(0, 0, 0, -30).center())
            p.drawImage(target, self.image)
        p.setPen(QColor('#c7e2f0'))
        stale = self.updated and time.monotonic()-self.updated > 3
        p.drawText(self.rect().adjusted(10, 0, -10, -5), Qt.AlignmentFlag.AlignBottom|Qt.AlignmentFlag.AlignLeft,
                   self.title+(' · 数据过期' if stale else ' · 双击放大' if self.image else ' · 等待数据'))
        p.end()
    def mouseDoubleClickEvent(self, event):
        if self.image is None: return
        dialog = QDialog(self); dialog.setWindowTitle(self.title); dialog.resize(1280, 780)
        tile = ImageTile(self.title, dialog); tile.image = self.image; tile.updated = self.updated
        layout = QVBoxLayout(dialog); layout.addWidget(tile)
        dialog.exec()


class SensorWall(Plugin):
    def __init__(self, context):
        super().__init__(context)
        self.setObjectName('CarlaSensorWall')
        self.node = context.node
        self.widget = QWidget(); self.widget.setWindowTitle('CARLA Sensor Wall')
        self.widget.resize(1500, 1000)
        self.widget.setStyleSheet('QWidget{background:#101c29;color:#e0edf5;font-size:14px}QLabel{padding:8px}')
        layout = QVBoxLayout(self.widget)
        layout.addWidget(QLabel('CARLA 六视角  ·  前后方向排列  ·  深度 / BEV 点云  ·  双击任一画面放大'))
        grid = QGridLayout(); grid.setSpacing(12); layout.addLayout(grid)
        names = [('front_left','左前'),('front','正前'),('front_right','右前'),
                 ('rear_left','左后'),('rear','正后'),('rear_right','右后'),
                 ('depth','正前深度 · 米值 / 0–80m 色阶'),('cloud','BEV 点云 · 前方朝上 · ±60m'),('bev','顶视 RGB')]
        self.tiles = {}; self.subscriptions = []; self.pending = {}; self.lock = threading.Lock()
        for index, (name, title) in enumerate(names):
            tile = ImageTile(title); self.tiles[name] = tile
            grid.addWidget(tile, index//3, index%3)
            topic = '/carla/ego/camera/'+name+'/image' if index < 6 else {
                'depth': '/carla/ego/depth/image', 'cloud': '/carla/ego/lidar/points', 'bev': '/carla/ego/bev/image'}[name]
            self.subscriptions.append(self.node.create_subscription(PointCloud2 if name == 'cloud' else Image,
                topic, lambda message, n=name: self.receive(n, message), qos_profile_sensor_data))
        for i in range(3): grid.setColumnStretch(i, 1); grid.setRowStretch(i, 1)
        self.timer = QTimer(self.widget); self.timer.timeout.connect(self.refresh); self.timer.start(100)
        context.add_widget(self.widget)
    def receive(self, name, message):
        with self.lock: self.pending[name] = message
    def refresh(self):
        with self.lock: pending, self.pending = self.pending, {}
        for name, message in pending.items():
            try: self.tiles[name].set_image(cloud_bev(message) if name == 'cloud' else rgb_message(message))
            except (ValueError, TypeError) as exc: self.node.get_logger().warning(str(exc))
        for tile in self.tiles.values(): tile.update()
    def shutdown_plugin(self):
        self.timer.stop()
        for subscription in self.subscriptions: self.node.destroy_subscription(subscription)

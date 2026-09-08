"""Exact model-input recording plus frame-matched auxiliary depth/LiDAR.

Runs in the process that owns simulation ticks. It never ticks or loads the world.
"""
from __future__ import annotations
import io
import json
import math
import os
import shutil
import threading
import time
import uuid
from pathlib import Path

import numpy as np
from PIL import Image

CAMERAS = ('CAM_FRONT', 'CAM_FRONT_LEFT', 'CAM_FRONT_RIGHT', 'CAM_BACK', 'CAM_BACK_LEFT', 'CAM_BACK_RIGHT')
POSES = ((.8, 0, 1.6, 0, 70), (.27, -.55, 1.6, -55, 70), (.27, .55, 1.6, 55, 70),
         (-2, 0, 1.6, 180, 110), (-.32, -.55, 1.6, -110, 70), (-.32, .55, 1.6, 110, 70))


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    tmp.replace(path)


def depth_meters(bgra):
    a = np.asarray(bgra, dtype=np.float32)
    return ((a[..., 2] + 256*a[..., 1] + 65536*a[..., 0]) * (1000.0/16777215.0)).astype(np.float32)


def depth_preview(depth):
    value = np.clip(np.log1p(depth)/np.log(81), 0, 1)
    return np.stack((255*(1-value), 210*(1-abs(value*2-1)), 255*value), axis=-1).astype('uint8')


def bev_preview(points, size=640, extent=60):
    canvas = np.full((size, size, 3), (9, 18, 29), dtype=np.uint8)
    for n in range(0, size, max(1, size//12)):
        canvas[n, :, :] = (22, 38, 48)
        canvas[:, n, :] = (22, 38, 48)
    if len(points):
        p = np.asarray(points)
        valid = np.isfinite(p[:, :3]).all(axis=1) & (np.abs(p[:, 0]) < extent) & (np.abs(p[:, 1]) < extent)
        p = p[valid]
        x = (size/2+p[:, 1]*size/(2*extent)).astype(int)
        y = (size/2-p[:, 0]*size/(2*extent)).astype(int)
        h = np.clip((p[:, 2]+3)/8, 0, 1)
        canvas[y, x] = np.stack((50+180*h, 230-80*h, 210-150*h), axis=1).astype('uint8')
    canvas[size//2-5:size//2+5, size//2-3:size//2+3] = (255, 255, 255)
    return canvas


def calibration(spec):
    result = dict(spec)
    if all(key in spec for key in ('x','y','z')):
        # Same convention as LibCarla geom/Rotation.h, including pitch/roll signs.
        p,y,r = (math.radians(float(spec.get(key,0))) for key in ('pitch','yaw','roll'))
        cp,sp,cy,sy,cr,sr = math.cos(p),math.sin(p),math.cos(y),math.sin(y),math.cos(r),math.sin(r)
        pose = np.eye(4)
        pose[:3,:3] = [[cp*cy,cy*sp*sr-sy*cr,-cy*sp*cr-sy*sr],
                       [cp*sy,sy*sp*sr+cy*cr,-sy*sp*cr+cy*sr],
                       [sp,-cp*sr,cp*cr]]
        pose[:3,3] = [float(spec[key]) for key in ('x','y','z')]
        if not np.isfinite(pose).all(): raise ValueError('Non-finite sensor pose')
        result['sensor_to_ego'] = pose.tolist()
        result['ego_to_sensor'] = np.linalg.inv(pose).tolist()
        result['transform_convention'] = 'column homogeneous vectors; metres; ego CARLA x forward/y right/z up'
    if spec['type'].startswith('sensor.camera'):
        w, h = int(spec['width']), int(spec['height'])
        f = w/(2*math.tan(math.radians(float(spec['fov']))/2))
        result['K'] = [[f, 0, w/2], [0, f, h/2], [0, 0, 1]]
        result['sensor_to_optical'] = [[0,1,0,0],[0,0,-1,0],[1,0,0,0],[0,0,0,1]]
    result['coordinates'] = 'CARLA sensor frame: x forward, y right, z up; camera pixels: x right, y down'
    return result


class SensorCapture:
    def __init__(self, world, ego, specs, runtime, source='model-input'):
        import carla
        if source not in ('model-input', 'sensor-rig'):
            raise ValueError('Unknown capture source')
        if source == 'sensor-rig' and specs:
            raise ValueError('Standalone rig owns its complete sensor configuration')
        self.source = source
        self.world, self.ego = world, ego
        self.map_name = world.get_map().name
        self.root = Path(runtime)
        self.live = self.root/'capture'
        self.live.mkdir(parents=True, exist_ok=True)
        self.samples, self.sensors = {}, []
        self.lock = threading.Condition()
        self.closed = False
        self.run = None
        self.count = self.skipped = self.bytes = 0
        self.last_request = None
        self.frame_index = []
        self.error = None
        self.sequence = 0
        self.live_generations = []
        self.specs = {s['id']: calibration(s) for s in specs}
        auxiliary = []
        for name, (x, y, z, yaw, fov) in zip(CAMERAS, POSES):
            camera = self.specs.get(name, dict(id=name, type='sensor.camera.rgb', x=x, y=y, z=z, yaw=yaw,
                                              pitch=0, roll=0, width=640, height=360, fov=fov))
            if name not in self.specs:
                auxiliary.append(camera)
            auxiliary.append({**camera, 'id': 'DEPTH_'+name, 'type': 'sensor.camera.depth',
                              'width': 640, 'height': max(32, round(640*camera['height']/camera['width']))})
        auxiliary += [dict(id='LIDAR', type='sensor.lidar.ray_cast', x=0, y=0, z=2.4,
                           yaw=0, pitch=0, roll=0, range=80, channels=32, points_per_second=128000,
                           rotation_frequency=20),
                      dict(id='BEV_RGB', type='sensor.camera.rgb', x=0, y=0, z=40, pitch=-90, yaw=0,
                           roll=0, width=512, height=512, fov=90)]
        self.auxiliary = {s['id'] for s in auxiliary}
        try:
            for spec in auxiliary:
                self.specs[spec['id']] = calibration(spec)
                bp = world.get_blueprint_library().find(spec['type'])
                for key in ('width', 'height', 'fov', 'range', 'channels', 'points_per_second', 'rotation_frequency'):
                    if key in spec:
                        bp.set_attribute({'width': 'image_size_x', 'height': 'image_size_y'}.get(key, key), str(spec[key]))
                bp.set_attribute('sensor_tick', '0.0')
                transform = carla.Transform(carla.Location(x=spec['x'], y=spec['y'], z=spec['z']),
                    carla.Rotation(pitch=spec.get('pitch', 0), yaw=spec.get('yaw', 0), roll=spec.get('roll', 0)))
                sensor = world.spawn_actor(bp, transform, attach_to=ego)
                self.sensors.append(sensor)
                sensor.listen(lambda data, name=spec['id']: self.receive(name, data))
            atomic_json(self.live/'calibration.json', self.specs)
        except BaseException:
            self.close()
            raise

    def receive(self, name, data):
        with self.lock:
            if self.closed:
                return
            if name == 'LIDAR':
                value = np.frombuffer(data.raw_data, dtype=np.float32).reshape(-1, 4).copy()
            else:
                value = np.frombuffer(data.raw_data, dtype=np.uint8).reshape(data.height, data.width, 4).copy()
            bucket = self.samples.setdefault(name, {})
            bucket[data.frame] = value
            for frame in sorted(bucket)[:-4]:
                del bucket[frame]
            self.lock.notify_all()

    def request(self):
        try:
            return json.loads((self.root/'collection-request.json').read_text())
        except (OSError, ValueError):
            return {'recording': False}

    def begin(self, request):
        base = Path(os.environ.get('CSA_DATASET_ROOT', str(self.root.parent.parent/'runs/datasets')))
        self.run_id = 'capture-'+time.strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:8]
        self.run = base/self.run_id
        self.run.mkdir(parents=True, exist_ok=False)
        self.count = self.skipped = self.bytes = 0
        self.frame_index = []
        self.error = None
        self.started = time.time()
        self.last_request = request['id']
        self.sampling_every = int(request.get('every',5))
        self.stop_reason = None
        self.execution_id = os.environ.get('CSA_EXECUTION_ID') or None
        atomic_json(self.run/'calibration.json', self.specs)
        self.manifest('recording')

    def manifest(self, status):
        if self.run is None:
            return
        atomic_json(self.run/'manifest.json', dict(schema_version='carla-safety-dataset/0.2',
            run_id=self.run_id, scenario_id=(os.environ.get('CSA_ALGORITHM_LABEL', 'model')+' closed-loop'
                                           if self.source == 'model-input' else 'standalone sensor rig'),
            map=self.map_name, family=self.source, status=status, started_at=self.started,
            completed_at=time.strftime('%Y-%m-%dT%H:%M:%S'), frame_count=self.count, skipped_frames=self.skipped,
            bytes=self.bytes, replay=True, model=os.environ.get('CSA_ALGORITHM_LABEL') if self.source == 'model-input' else None,
            sensors={name: {'samples': self.count, 'format': 'png/npy/npz', 'path': 'samples'} for name in self.specs},
            files={'calibration': 'calibration.json', 'index': 'index.json'}, error=self.error,
            input_archive='model_input.npz' if self.source == 'model-input' else 'sensor_input.npz',
            sampling_every_frames=self.sampling_every,
            execution_id=self.execution_id,
            cleanup_errors=getattr(self,'cleanup_errors',[]),
            stop_reason=getattr(self,'stop_reason',None),
            notes=[('model_input.npz contains exact pre-model arrays; RGB PNG is lossless RGB conversion'
                    if self.source == 'model-input' else
                    'sensor_input.npz contains raw rig RGB BGRA arrays; no model was invoked'),
                   'Depth is auxiliary 640px-wide float32 metres with source camera aspect ratio; LiDAR XYZI is auxiliary, not claimed model input',
                   'BEV point projection is derived, BEV_RGB is rendered top-down, not semantic ground truth']))
        atomic_json(self.run/'index.json', {'frames': self.frame_index})

    def process_frame(self, frame, control):
        """Record an owner-supplied CARLA tick without fabricating model input."""
        if self.source != 'sensor-rig': raise ValueError('process_frame requires sensor-rig mode')
        if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0:
            raise ValueError('Frame must be a non-negative integer')
        return self.process({}, None, control, frame_id=frame)

    def process(self, input_data, agent, control, frame_id=None):
        if self.closed:
            return
        req = self.request()
        if self.run is not None and (not req.get('recording') or req.get('id') != self.last_request):
            self.manifest('saved')
            self.run = None
        if req.get('recording') and req.get('id') != self.last_request:
            self.begin(req)
        self.sequence += 1
        camera_frames = [int(input_data[n][0]) for n in CAMERAS if n in input_data]
        if frame_id is not None:
            if self.source != 'sensor-rig' or input_data:
                raise ValueError('Explicit frame is only valid for standalone sensor rig')
            camera_frames = [frame_id]
        if not camera_frames:
            return
        frame = max(camera_frames)
        # Copy exact-frame auxiliary data only. Never pair an older image with new model input.
        with self.lock:
            self.lock.wait_for(lambda: self.closed or all(frame in self.samples.get(n, {}) for n in self.auxiliary), timeout=.4)
            aux = {n: self.samples[n][frame] for n in self.auxiliary if frame in self.samples.get(n, {})}
        missing = sorted(self.auxiliary-set(aux))
        arrays = {n: np.asarray(v[1]).copy() for n, v in input_data.items() if not isinstance(v[1], dict)}
        arrays = {n: a for n, a in arrays.items() if a.dtype != object}
        rgb = {n: (arrays[n] if n in arrays else aux.get(n)) for n in CAMERAS}
        if self.source == 'sensor-rig':
            arrays = {n: value for n, value in rgb.items() if value is not None}
        outputs = getattr(agent, 'pid_metadata', {})
        def safe(value):
            if isinstance(value, dict): return {k: safe(v) for k, v in value.items()}
            if isinstance(value, (list, tuple)): return [safe(v) for v in value]
            if isinstance(value, np.ndarray): return safe(value.tolist())
            if isinstance(value, np.generic): return safe(value.item())
            if isinstance(value, float) and not math.isfinite(value): return None
            return value
        transform = self.ego.get_transform()
        snapshot = self.world.get_snapshot()
        metadata = dict(frame=frame, model_step=getattr(agent, 'step', None), timestamp=snapshot.timestamp.elapsed_seconds,
            source=self.source,
            model=os.environ.get('CSA_ALGORITHM_LABEL', type(agent).__name__) if self.source == 'model-input' else None,
            sensor_frames={n: int(v[0]) for n, v in input_data.items()},
            auxiliary_frames={n: frame for n in aux}, missing=missing,
            synchronized=not missing and len(set(camera_frames)) == 1,
            actual_model_inputs=list(input_data), outputs=safe(outputs),
            control={n: float(getattr(control, n)) for n in ('steer', 'throttle', 'brake')},
            ego={'id': self.ego.id, 'matrix': transform.get_matrix(), 'velocity': vars_vector(self.ego.get_velocity())})
        metadata['trajectory_ego_m'] = safe(outputs.get('plan', [outputs[k] for k in ('wp_1', 'wp_2', 'wp_3', 'wp_4') if k in outputs]))
        # Keep lightweight live previews atomic. Recording remains full resolution.
        generation = self.live/'frames'/str(frame)
        generation.mkdir(parents=True, exist_ok=True)
        for name, data in rgb.items():
            if data is not None:
                self.image(generation/(name+'.jpg'), data[:, :, :3][:, :, ::-1])
        for name, data in aux.items():
            if name.startswith('DEPTH_'):
                depth = depth_meters(data)
                self.image(generation/(name+'.jpg'), depth_preview(depth))
                np.save(generation/(name+'.npy'), depth, allow_pickle=False)
        if 'LIDAR' in aux:
            self.image(generation/'BEV_POINTS.jpg', bev_preview(aux['LIDAR']))
            np.save(generation/'LIDAR.npy', aux['LIDAR'], allow_pickle=False)
        if 'BEV_RGB' in aux:
            self.image(generation/'BEV_RGB.jpg', aux['BEV_RGB'][:, :, :3][:, :, ::-1])
        metadata['available'] = [n for n, d in rgb.items() if d is not None]+list(aux)+(['BEV_POINTS'] if 'LIDAR' in aux else [])
        metadata['recording'] = self.run is not None
        metadata['run_id'] = self.run_id if self.run else None
        metadata['recorded_frames'] = self.count
        metadata['error'] = self.error
        metadata['updated_at'] = time.time()
        metadata['generation'] = str(generation.relative_to(self.live))
        atomic_json(self.live/'latest.json', metadata)
        self.live_generations.append(generation)
        if len(self.live_generations) > 6:
            expired = self.live_generations.pop(0)
            for file in expired.iterdir():
                file.unlink()
            expired.rmdir()
        if self.run is None or self.sequence % max(1, int(req.get('every', 5))) != 0:
            return
        if not metadata['synchronized']:
            self.skipped += 1
            return
        if self.count >= int(req.get('max_frames', 2000)) or self.bytes > 20*1024**3 or shutil.disk_usage(self.run).free < 1024**3:
            self.stop_reason = ('frame_limit' if self.count >= int(req.get('max_frames',2000)) else
                                'storage_limit' if self.bytes > 20*1024**3 else 'disk_reserve')
            self.error = 'Recording stopped at frame/storage limit; existing samples preserved'
            self.manifest('saved_limit')
            self.run = None
            return
        folder = self.run/'samples'/f'{frame:010d}'
        folder.mkdir(parents=True, exist_ok=False)
        archive = 'model_input.npz' if self.source == 'model-input' else 'sensor_input.npz'
        metadata['input_archive'] = archive
        np.savez(folder/archive, **arrays)
        metadata['input_scalars'] = safe({n: v[1] for n, v in input_data.items() if isinstance(v[1], dict)})
        for name, data in rgb.items():
            Image.fromarray(data[:, :, :3][:, :, ::-1]).save(folder/(name+'.png'))
        for name, data in aux.items():
            if name.startswith('DEPTH_'):
                depth = depth_meters(data)
                np.save(folder/(name+'.npy'), depth, allow_pickle=False)
                Image.fromarray(depth_preview(depth)).save(folder/(name+'.png'))
        if 'LIDAR' in aux:
            np.save(folder/'LIDAR.npy', aux['LIDAR'], allow_pickle=False)
            Image.fromarray(bev_preview(aux['LIDAR'])).save(folder/'BEV_POINTS.png')
        if 'BEV_RGB' in aux:
            Image.fromarray(aux['BEV_RGB'][:, :, :3][:, :, ::-1]).save(folder/'BEV_RGB.png')
        metadata['actors'] = [{'id': a.id, 'type': a.type_id, 'matrix': a.get_transform().get_matrix(),
            'extent': vars_vector(a.bounding_box.extent)} for a in self.world.get_actors()
            if a.type_id.startswith(('vehicle.', 'walker.', 'static.prop.')) and a.get_location().distance(self.ego.get_location()) < 80]
        atomic_json(folder/'frame.json', metadata)
        self.frame_index.append({'frame': frame, 'timestamp': metadata['timestamp'], 'path': str(folder.relative_to(self.run))})
        self.count += 1
        self.bytes += sum(p.stat().st_size for p in folder.iterdir())
        self.manifest('recording')

    def image(self, path, value):
        image = Image.fromarray(np.ascontiguousarray(value))
        image.thumbnail((960, 540))
        temporary = path.with_suffix('.tmp.jpg')
        image.save(temporary, quality=85)
        temporary.replace(path)

    def close(self):
        errors=[]
        with self.lock:
            self.closed = True
            self.lock.notify_all()
        for sensor in self.sensors:
            try:
                if sensor.is_alive: sensor.stop()
            except Exception as exc: errors.append(f'Sensor stop: {exc}')
        remaining=[]
        for sensor in self.sensors:
            try:
                if sensor.is_alive and sensor.destroy() is False:
                    raise RuntimeError('destroy returned false')
            except Exception as exc:
                errors.append(f'Sensor destroy: {exc}')
                remaining.append(sensor)
        self.sensors=remaining
        self.cleanup_errors=errors
        try:
            self.manifest('saved_cleanup_error' if errors else 'saved')
        except OSError as exc:
            print(f'Unable to finalize capture manifest; committed samples retained: {exc}', flush=True)
            errors.append(f'Manifest finalization: {exc}')
        self.run = None
        if errors: print('Capture cleanup errors: '+ '; '.join(errors),flush=True)
        return errors


def vars_vector(v):
    return {'x': v.x, 'y': v.y, 'z': v.z}


def capture_agent(base):
    """Wrap a model without changing its sensor interface or planning output."""
    class CapturedAgent(base):
        _capture = None
        _capture_failed = False

        def run_step(self, input_data, timestamp):
            if os.environ.get('CSA_SENSOR_CAPTURE') == '1' and not self._capture_failed:
                try:
                    if self._capture is None:
                        from srunner.scenariomanager.carla_data_provider import CarlaDataProvider
                        world = CarlaDataProvider.get_world()
                        hero = next(a for a in world.get_actors().filter('vehicle.*') if a.attributes.get('role_name') == 'hero')
                        self._capture = SensorCapture(world, hero, self.sensors(), os.environ['CSA_EVALUATION_CONTROL_DIR'])
                except Exception as exc:
                    self._capture_failed = True
                    try:
                        atomic_json(Path(os.environ['CSA_EVALUATION_CONTROL_DIR'])/'capture/latest.json', {'error': str(exc), 'available': []})
                    except OSError:
                        pass  # Reporting a full disk must not abort model inference.
                    print(f'Sensor capture unavailable: {exc}', flush=True)
            exact_input = {k: (v[0], v[1].copy() if hasattr(v[1], 'copy') else v[1]) for k, v in input_data.items()} if self._capture else None
            control = super().run_step(input_data, timestamp)
            if self._capture:
                try:
                    self._capture.process(exact_input, self, control)
                except Exception as exc:
                    self._capture.error = str(exc)
                    self._capture.close()
                    self._capture = None
                    self._capture_failed = True
                    try:
                        atomic_json(Path(os.environ['CSA_EVALUATION_CONTROL_DIR'])/'capture/latest.json', {'error': str(exc), 'available': []})
                    except OSError:
                        pass
                    print(f'Recording failed, model remains running: {exc}', flush=True)
            return control

        def destroy(self):
            if self._capture:
                self._capture.close()
                self._capture = None
            return super().destroy()
    return CapturedAgent

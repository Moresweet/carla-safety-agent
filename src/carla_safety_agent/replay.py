"""Read-only, path-confined dataset playback API helpers."""
import json
from pathlib import Path


def dataset_path(root, run_id):
    root = Path(root).resolve()
    path = (root/run_id).resolve()
    if path.parent != root or not (path/'manifest.json').is_file():
        raise ValueError('Unknown dataset')
    return path


def replay_index(root, run_id):
    path = dataset_path(root, run_id)
    if not (path/'index.json').is_file():
        return {'frames': [], 'legacy': True, 'message': '旧数据没有同步帧索引，不能冒充六视角回放'}
    return json.loads((path/'index.json').read_text())


def replay_file(root, run_id, frame, name):
    path = dataset_path(root, run_id)
    index = replay_index(root, run_id)
    entry = next((v for v in index['frames'] if v['frame'] == int(frame)), None)
    if not entry or Path(name).name != name:
        raise ValueError('Unknown frame/file')
    folder = (path/entry['path']).resolve()
    target = (folder/name).resolve()
    if not folder.is_relative_to(path) or target.parent != folder or not target.is_file():
        raise ValueError('File is outside this recorded frame')
    return target


def replay_projection(root, run_id, frame, camera):
    """Bounded diagnostic overlay payload, not an occlusion-correct point label."""
    import numpy as np
    from .projection import project_points
    from .sensor_capture import CAMERAS
    if camera not in CAMERAS:
        raise ValueError('Unknown camera')
    dataset=dataset_path(root,run_id)
    path=(dataset/'calibration.json').resolve()
    if path.parent != dataset:
        raise ValueError('Calibration is outside dataset')
    calibration=json.loads(path.read_text())
    points=np.load(replay_file(root,run_id,frame,'LIDAR.npy'),allow_pickle=False,mmap_mode='r')
    if points.ndim != 2 or points.shape[1] != 4 or points.dtype.kind not in 'fiu' or len(points)>1000000:
        raise ValueError('Invalid or oversized point cloud')
    if 'LIDAR' not in calibration or camera not in calibration:
        raise ValueError('Missing recorded sensor calibration')
    result=project_points(points,calibration['LIDAR'],calibration[camera])
    count=len(result['indices'])
    stride=max(1,(count+4999)//5000)
    return {'frame':int(frame),'camera':camera,'width':calibration[camera]['width'],
            'height':calibration[camera]['height'],'visible_count':count,
            'pixels':result['pixels'][::stride].tolist(),'depth':result['depth'][::stride].tolist(),
            'point_indices':result['indices'][::stride].tolist(),
            'occlusion_checked':False,'sample_stride':stride}


def replay_trajectory(root, run_id, frame, horizon_s=5.0):
    """Recorded ego positions, not predictions or interpolated future ground truth."""
    import numpy as np
    if isinstance(horizon_s,bool) or not isinstance(horizon_s,(int,float)) or not 0<horizon_s<=30:
        raise ValueError('Trajectory horizon must be 0..30 seconds')
    entries=replay_index(root,run_id)['frames']
    current=next((e for e in entries if e['frame']==int(frame)),None)
    if current is None: raise ValueError('Unknown frame')
    metadata=json.loads(replay_file(root,run_id,frame,'frame.json').read_text())
    pose=np.asarray(metadata['ego']['matrix'],dtype=float)
    if pose.shape!=(4,4) or not np.isfinite(pose).all(): raise ValueError('Invalid ego pose')
    try: inverse=np.linalg.inv(pose)
    except np.linalg.LinAlgError as exc: raise ValueError('Invalid ego pose') from exc
    timestamp=float(metadata['timestamp'])
    if not np.isfinite(timestamp): raise ValueError('Invalid timestamp')
    selected=[e for e in entries if abs(float(e['timestamp'])-timestamp)<=horizon_s]
    if len(selected)>2000: raise ValueError('Trajectory window exceeds 2000 samples')
    history,future=[],[]
    for entry in selected:
        record=json.loads(replay_file(root,run_id,entry['frame'],'frame.json').read_text())
        matrix=np.asarray(record['ego']['matrix'],dtype=float)
        if matrix.shape!=(4,4) or not np.isfinite(matrix).all(): raise ValueError('Invalid recorded ego pose')
        dt=float(record['timestamp'])-timestamp
        if not np.isfinite(dt) or abs(dt)>horizon_s: raise ValueError('Index timestamp mismatch')
        xyz=(inverse @ matrix[:,3])[:3].tolist()
        point={'frame':entry['frame'],'dt_s':dt,'xyz_m':xyz}
        (history if dt<=0 else future).append(point)
    return {'frame':int(frame),'history':history,'future':future,'source':'recorded_ego_pose',
            'coordinates':'current ego CARLA x forward, y right, z up',
            'interpolated':False,'horizon_s':horizon_s}

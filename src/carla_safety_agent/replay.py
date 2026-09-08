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

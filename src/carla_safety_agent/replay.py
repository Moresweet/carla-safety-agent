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
    result=json.loads((path/'index.json').read_text())
    from .data_quality import temporal_quality
    manifest=json.loads((path/'manifest.json').read_text())
    result['temporal_quality']=temporal_quality(result['frames'],manifest.get('sampling_every_frames'))
    return result


def replay_editor_events(root, run_id):
    from .editor_events import editor_events
    path = dataset_path(root,run_id)
    manifest = json.loads((path/'manifest.json').read_text())
    reference = manifest.get('files',{}).get('editor_events')
    if reference is None:
        return {'available':False,'events':[],'message':'此录制没有归档编辑事件'}
    archive = path/'editor-events.json'
    if reference != archive.name or archive.is_symlink() or archive.stat().st_size>32*1024*1024:
        raise ValueError('Invalid editor event archive')
    document = json.loads(archive.read_text())
    if not isinstance(document,dict) or document.get('schema_version') != 'carla-editor-events/1' or document.get('execution_id') != manifest.get('execution_id'):
        raise ValueError('Editor archive identity mismatch')
    frames = [entry['frame'] for entry in replay_index(root,run_id)['frames']]
    events = editor_events(document['records'],frames,manifest['execution_id'])
    if events != document.get('events'):
        raise ValueError('Editor event index differs from audit records')
    return {'available':True,'execution_id':manifest['execution_id'],'events':events}


def replay_file(root, run_id, frame, name):
    path = dataset_path(root, run_id)
    index = replay_index(root, run_id)
    entry = next((v for v in index['frames'] if v['frame'] == int(frame)), None)
    return _indexed_file(path,entry,name)


def replay_events(root, run_id):
    """Index recorded braking segments, never infer collisions from controls."""
    import math
    path = dataset_path(root, run_id)
    index = replay_index(root, run_id)
    entries = index.get('frames', [])
    if index.get('legacy') or not index['temporal_quality']['temporal_order_valid']:
        raise ValueError('A valid temporal index is required for event lookup')
    if len(entries) > 10000:
        raise ValueError('Event indexing supports at most 10000 recorded samples')
    events = []
    active = None
    previous = None
    cadence = index['temporal_quality']['sampling_every_frames']
    for entry in entries:
        record = json.loads(_indexed_file(path, entry, 'frame.json').read_text())
        if record.get('frame') != entry['frame'] or record.get('timestamp') != entry['timestamp']:
            raise ValueError('Index/sample identity mismatch')
        control = record.get('control')
        brake = control.get('brake') if isinstance(control, dict) else None
        if (isinstance(brake, bool) or not isinstance(brake, (int, float)) or
                not math.isfinite(brake) or not 0 <= brake <= 1):
            raise ValueError('Missing or invalid recorded brake control')
        # Do not join known recording gaps into one continuous braking segment.
        if previous is not None and cadence is not None and entry['frame'] - previous != cadence:
            active = None
        if brake >= 0.5:
            if active is None:
                active = {'kind':'brake_segment', 'start_frame':entry['frame'],
                    'start_timestamp':entry['timestamp'], 'sample_count':0, 'peak_brake':brake}
                events.append(active)
            active.update(end_frame=entry['frame'], end_timestamp=entry['timestamp'],
                          sample_count=active['sample_count'] + 1,
                          peak_brake=max(active['peak_brake'], brake))
        else:
            active = None
        previous = entry['frame']
    collisions = recorded_collisions(path, entries)
    return {'events':events, 'source':'recorded_control', 'brake_threshold':0.5,
            'sample_count':len(entries), 'collision_detection_available':collisions['available'],
            'collisions':collisions,
            'note':'Braking segments are not collision or danger labels; boundaries use saved samples only.'}


def recorded_collisions(dataset, entries):
    """Keep native event time separate from the closest available replay sample."""
    import bisect
    from .scene_store import finite_number
    file = (dataset / 'collisions.json').resolve()
    if file.parent != dataset:
        raise ValueError('Collision file outside dataset')
    if not file.exists():
        manifest = json.loads((dataset / 'manifest.json').read_text())
        if manifest.get('files', {}).get('collisions'):
            raise ValueError('Declared collision recording is missing')
        return {'available':False, 'events':[], 'note':'No native collision recording in this dataset'}
    if file.stat().st_size > 16*1024*1024:
        raise ValueError('Oversized collision metadata')
    payload = json.loads(file.read_text())
    if (not isinstance(payload, dict) or payload.get('schema_version') != 'carla-collision-events/1'
            or payload.get('source') != 'sensor.other.collision'
            or not isinstance(payload.get('events'), list) or len(payload['events']) > 10000):
        raise ValueError('Invalid native collision metadata')
    for name in ('buffer_dropped_since_sensor_start', 'invalid_observations_since_sensor_start'):
        value = payload.get(name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError('Invalid collision quality counter')
    frames = [entry['frame'] for entry in entries]
    events = []
    for event in payload['events']:
        if not isinstance(event, dict): raise ValueError('Invalid collision event')
        frame, impulse = event.get('frame'), event.get('normal_impulse')
        actor = event.get('other_actor_id')
        if (event.get('kind') != 'collision' or isinstance(frame, bool) or not isinstance(frame, int)
                or frame < 0 or not finite_number(event.get('timestamp'))
                or isinstance(actor, bool) or not isinstance(actor, int) or actor < 0
                or not isinstance(event.get('other_actor_type'), str)
                or not isinstance(impulse, dict) or set(impulse) != {'x','y','z'}
                or not all(finite_number(value) for value in impulse.values())):
            raise ValueError('Invalid collision event')
        position = bisect.bisect_left(frames, frame)
        candidates = [entries[i] for i in (position-1, position) if 0 <= i < len(entries)]
        nearest = min(candidates, key=lambda entry:abs(entry['frame']-frame)) if candidates else None
        events.append({**event, 'replay_frame':nearest['frame'] if nearest else None,
            'exact_saved_frame':nearest is not None and nearest['frame']==frame,
            'replay_time_offset_s':nearest['timestamp']-event['timestamp'] if nearest else None})
    return {**payload, 'available':True, 'events':sorted(events,key=lambda event:(event['frame'],event['timestamp']))}


def _indexed_file(path, entry, name):
    """Resolve an already selected index entry without rereading the full index."""
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
    path=dataset_path(root,run_id)
    index=replay_index(root,run_id)
    if not index.get('temporal_quality',{}).get('temporal_order_valid',False):
        raise ValueError('Invalid temporal index')
    entries=index['frames']
    current=next((e for e in entries if e['frame']==int(frame)),None)
    if current is None: raise ValueError('Unknown frame')
    metadata=json.loads(_indexed_file(path,current,'frame.json').read_text())
    pose=np.asarray(metadata['ego']['matrix'],dtype=float)
    if pose.shape!=(4,4) or not np.isfinite(pose).all(): raise ValueError('Invalid ego pose')
    try: inverse=np.linalg.inv(pose)
    except np.linalg.LinAlgError as exc: raise ValueError('Invalid ego pose') from exc
    timestamp=float(metadata['timestamp'])
    if not np.isfinite(timestamp): raise ValueError('Invalid timestamp')
    if metadata['frame']!=int(frame) or timestamp!=float(current['timestamp']):
        raise ValueError('Index/sample identity mismatch')
    selected=[e for e in entries if abs(float(e['timestamp'])-timestamp)<=horizon_s]
    if len(selected)>2000: raise ValueError('Trajectory window exceeds 2000 samples')
    history,future=[],[]
    for entry in selected:
        record=json.loads(_indexed_file(path,entry,'frame.json').read_text())
        if record['frame']!=entry['frame'] or float(record['timestamp'])!=float(entry['timestamp']):
            raise ValueError('Index/sample identity mismatch')
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

"""Temporal index audit. Gaps are observations, not inferred sensor drop counts."""
import math


def validate_ego_pose(value):
    """Return a rigid CARLA body-to-world transform; never repair saved data."""
    import numpy as np
    try:
        matrix = np.asarray(value, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError('Recorded trajectory requires rigid ego poses') from exc
    if (matrix.shape != (4, 4) or not np.isfinite(matrix).all()
            or not np.allclose(matrix[3], [0, 0, 0, 1], rtol=0, atol=1e-6)
            or not np.allclose(matrix[:3, :3].T @ matrix[:3, :3], np.eye(3), rtol=0, atol=1e-5)
            or not np.isclose(np.linalg.det(matrix[:3, :3]), 1, rtol=0, atol=1e-5)):
        raise ValueError('Recorded trajectory requires rigid ego poses')
    return matrix


def validate_capture_frame(metadata, entry, required_sensors):
    """Verify source frame IDs instead of trusting the synchronized summary flag."""
    frame=entry['frame']
    timestamp=metadata.get('timestamp')
    if (isinstance(metadata.get('frame'),bool) or not isinstance(metadata.get('frame'),int) or
            isinstance(timestamp,bool) or not isinstance(timestamp,(int,float)) or not math.isfinite(timestamp) or
            metadata.get('frame')!=frame or timestamp!=entry['timestamp'] or
            metadata.get('synchronized') is not True or metadata.get('missing')!=[]):
        raise ValueError('Sample/index identity or synchronization mismatch')
    tables=[metadata.get('sensor_frames'),metadata.get('auxiliary_frames')]
    if any(not isinstance(table,dict) for table in tables):
        raise ValueError('Missing recorded sensor frame identities')
    for table in tables:
        if any(not isinstance(name,str) or not name or isinstance(value,bool) or
               not isinstance(value,int) or value!=frame for name,value in table.items()):
            raise ValueError('Recorded sensor frames are not synchronized')
    present=set(tables[0])|set(tables[1])
    if not set(required_sensors)<=present:
        raise ValueError('Required sensor frame identity missing')
    if not set(metadata.get('actual_model_inputs',[]))<=set(tables[0]):
        raise ValueError('Model input frame identity missing')


def validate_capture_index(entries, manifest):
    """Reject ambiguous sample identities before opening any indexed sample."""
    if not isinstance(entries, list) or not entries:
        raise ValueError('No recorded samples')
    if any(not isinstance(entry, dict) for entry in entries):
        raise ValueError('Invalid sample index')
    quality = temporal_quality(entries, manifest.get('sampling_every_frames'))
    if not quality['temporal_order_valid']:
        raise ValueError('Invalid sample frame/timestamp order')
    count = manifest.get('frame_count')
    if isinstance(count, bool) or not isinstance(count, int) or count != len(entries):
        raise ValueError('Manifest/index sample count mismatch')
    for entry in entries:
        if entry.get('path') != f"samples/{entry['frame']:010d}":
            raise ValueError('Index sample path does not match frame identity')
    return quality


def temporal_quality(entries, sampling_every=None):
    if sampling_every is not None and (isinstance(sampling_every,bool) or
        not isinstance(sampling_every,int) or sampling_every<1):
        raise ValueError('Invalid sampling interval')
    errors,gaps=[],[]
    previous=None
    for offset,entry in enumerate(entries):
        frame,timestamp=entry.get('frame'),entry.get('timestamp')
        if (isinstance(frame,bool) or not isinstance(frame,int) or frame<0 or
            isinstance(timestamp,bool) or not isinstance(timestamp,(int,float)) or
            not math.isfinite(timestamp)):
            errors.append({'index':offset,'reason':'invalid_frame_or_timestamp'})
            previous=None
            continue
        if previous is not None:
            df,dt=frame-previous['frame'],timestamp-previous['timestamp']
            if df<=0 or dt<=0:
                errors.append({'index':offset,'reason':'non_monotonic','frame_delta':df,'time_delta_s':dt})
            elif sampling_every is not None and df!=sampling_every:
                gaps.append({'from_frame':previous['frame'],'to_frame':frame,
                             'frame_delta':df,'time_delta_s':dt})
        previous=entry
    return {'sample_count':len(entries),'sampling_every_frames':sampling_every,
            'temporal_order_valid':not errors,'errors':errors,'unexpected_intervals':gaps,
            'gap_check_available':sampling_every is not None,
            'note':'Unexpected intervals can reflect skipped captures or recording pauses; not sensor drop counts.'}

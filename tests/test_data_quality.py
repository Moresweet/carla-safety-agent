from carla_safety_agent.data_quality import temporal_quality
import pytest


@pytest.mark.parametrize('matrix', [None, {}, [], [[1, 2], [3]], 'invalid'])
def test_missing_or_malformed_ego_pose_is_explicit(matrix):
    from carla_safety_agent.data_quality import validate_ego_pose
    with pytest.raises(ValueError, match='rigid ego poses'):
        validate_ego_pose(matrix)


def test_raw_validator_reports_corrupt_pose_frame(tmp_path):
    import json
    import os
    import subprocess
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    (tmp_path / 'manifest.json').write_text(json.dumps({'frame_count': 1}))
    (tmp_path / 'index.json').write_text(json.dumps({'frames': [
        {'frame': 42, 'timestamp': 2.1, 'path': 'samples/0000000042'}]}))
    (tmp_path / 'calibration.json').write_text('{}')
    sample = tmp_path / 'samples/0000000042'
    sample.mkdir(parents=True)
    (sample / 'frame.json').write_text(json.dumps({'ego': {'matrix': [1, 2, 3]}}))
    result = subprocess.run([sys.executable, str(root / 'tools/validate_capture_dataset.py'), str(tmp_path)],
        env={**os.environ, 'PYTHONPATH': str(root / 'src')}, capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert 'Invalid recorded ego pose at frame 42' in result.stderr
    assert 'PASS:' not in result.stdout
    from carla_safety_agent.capture_quality import audit_capture
    report = audit_capture(tmp_path, root / 'tools/validate_capture_dataset.py', sys.executable)
    assert report['state'] == 'failed'
    assert report['reason_code'] == 'invalid_ego_pose'
    assert report['problem_frame'] == 42


def test_sampling_does_not_count_normal_downsampling_as_missing():
    entries=[{'frame':f,'timestamp':f*.05} for f in (3,6,12)]
    result=temporal_quality(entries,3)
    assert result['temporal_order_valid']
    assert len(result['unexpected_intervals'])==1
    assert result['unexpected_intervals'][0]['from_frame']==6
    assert not temporal_quality(entries)['gap_check_available']


def test_bad_temporal_order_is_explicit():
    result=temporal_quality([{'frame':3,'timestamp':1},{'frame':3,'timestamp':1},
                             {'frame':4,'timestamp':float('nan')}],1)
    assert not result['temporal_order_valid'] and len(result['errors'])==2

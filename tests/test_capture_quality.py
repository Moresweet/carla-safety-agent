import subprocess
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from carla_safety_agent.capture_quality import audit_capture
from carla_safety_agent.data_quality import validate_capture_index, validate_capture_frame


def test_real_empty_quota_recording_never_passes_quality(tmp_path):
    (tmp_path/'manifest.json').write_text(json.dumps({
        'schema_version':'carla-safety-dataset/0.2','status':'saved_limit',
        'frame_count':0,'stop_reason':'capture_quota','input_archive':'sensor_input.npz'}))
    (tmp_path/'index.json').write_text(json.dumps({'frames':[]}))
    (tmp_path/'calibration.json').write_text('{}')
    before={path.name:path.read_bytes() for path in tmp_path.iterdir()}
    validator=Path(__file__).resolve().parents[1]/'tools/validate_capture_dataset.py'
    report=audit_capture(tmp_path,validator,sys.executable)
    assert report['state']=='failed' and report['returncode']!=0
    assert report['reason_code']=='no_samples'
    assert 'No recorded samples' in report['detail']
    assert {path.name:path.read_bytes() for path in tmp_path.iterdir()}==before


def test_index_identity_and_count():
    entries = [{'frame': 4, 'timestamp': 1., 'path': 'samples/0000000004'}]
    assert validate_capture_index(entries, {'frame_count': 1})['temporal_order_valid']
    for changed in ({'path': '../outside'}, {'timestamp': float('nan')}, {'frame': True}):
        with pytest.raises(ValueError):
            validate_capture_index([{**entries[0], **changed}], {'frame_count': 1})
    for count in (True, 0, 2, None):
        with pytest.raises(ValueError):
            validate_capture_index(entries, {'frame_count': count})


def test_sensor_frame_summary_cannot_hide_misaligned_or_missing_sources():
    entry={'frame':5,'timestamp':1.}
    metadata={**entry,'synchronized':True,'missing':[],'actual_model_inputs':['CAM_FRONT'],
              'sensor_frames':{'CAM_FRONT':5},'auxiliary_frames':{'LIDAR':5}}
    validate_capture_frame(metadata,entry,['CAM_FRONT','LIDAR'])
    for changed in ({'auxiliary_frames':{'LIDAR':4}}, {'sensor_frames':{}},
                    {'sensor_frames':{'CAM_FRONT':True}}, {'auxiliary_frames':None}):
        with pytest.raises(ValueError):
            validate_capture_frame({**metadata,**changed},entry,['CAM_FRONT','LIDAR'])


@pytest.mark.parametrize('code,state', [(0, 'passed'), (1, 'failed'), (-11, 'failed')])
def test_subprocess_result_and_optimization_guard(monkeypatch, code, state):
    monkeypatch.setenv('PYTHONOPTIMIZE', '1')
    with patch('subprocess.run', return_value=subprocess.CompletedProcess([], code, 'output', 'error')) as run:
        report = audit_capture('/tmp/sample', '/tmp/validator.py', '/usr/bin/python3')
    assert report['state'] == state
    assert report['returncode'] == code
    assert 'PYTHONOPTIMIZE' not in run.call_args.kwargs['env']
    assert run.call_args.kwargs['timeout'] == 300


@pytest.mark.parametrize('error', [subprocess.TimeoutExpired('audit', 1), OSError('missing interpreter')])
def test_unavailable_check_is_not_a_pass(error):
    with patch('subprocess.run', side_effect=error):
        report = audit_capture('/tmp/sample', '/tmp/validator.py', '/usr/bin/python3')
    assert report['state'] == 'incomplete'
    assert report['returncode'] is None
    assert report['reason_code'] == ('validation_timeout' if isinstance(error,subprocess.TimeoutExpired) else 'validator_unavailable')


@pytest.mark.parametrize('output', ['CSA_CAPTURE_QUALITY=bad',
    'CSA_CAPTURE_QUALITY={"schema_version":"capture-quality-reason/1","reason_code":"invented"}',
    'ValueError: No recorded samples'])
def test_unknown_reason_protocol_keeps_generic_failure(output):
    with patch('subprocess.run',return_value=subprocess.CompletedProcess([],1,output,'')):
        report=audit_capture('/tmp/sample','/tmp/validator.py','/usr/bin/python3')
    assert report['reason_code']=='validation_failed'


@pytest.mark.parametrize('frame', [True, -1, 1.5, '42', None, 9007199254740992])
def test_pose_failure_protocol_rejects_invalid_frame(frame):
    line = 'CSA_CAPTURE_QUALITY=' + json.dumps({'schema_version': 'capture-quality-reason/1',
        'reason_code': 'invalid_ego_pose', 'frame': frame})
    with patch('subprocess.run', return_value=subprocess.CompletedProcess([], 1, line, '')):
        report = audit_capture('/tmp/sample', '/tmp/validator.py', '/usr/bin/python3')
    assert report['reason_code'] == 'validation_failed'
    assert report['problem_frame'] is None


@pytest.mark.parametrize('code,duplicate,extra', [(0, False, False), (1, True, False), (1, False, True)])
def test_pose_failure_protocol_requires_unique_failed_result(code, duplicate, extra):
    value = {'schema_version': 'capture-quality-reason/1', 'reason_code': 'invalid_ego_pose', 'frame': 42}
    if extra: value['unexpected'] = True
    line = 'CSA_CAPTURE_QUALITY=' + json.dumps(value)
    if duplicate: line += '\n' + line
    with patch('subprocess.run', return_value=subprocess.CompletedProcess([], code, line, '')):
        report = audit_capture('/tmp/sample', '/tmp/validator.py', '/usr/bin/python3')
    assert report['reason_code'] == (None if code == 0 else 'validation_failed')
    assert report['problem_frame'] is None


def test_real_validator_receives_inherited_descriptor(tmp_path):
    import fcntl
    script = tmp_path / 'validator.py'
    lock_path = tmp_path / 'scan.lock'
    with lock_path.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        script.write_text('import os\n'
                          f'os.fstat({lock.fileno()})\n'
                          'print("inherited descriptor verified")\n')
        report = audit_capture(tmp_path, script, sys.executable, pass_fds=(lock.fileno(),))
        assert report['state'] == 'passed' and report['returncode'] == 0
        assert 'inherited descriptor verified' in report['detail']

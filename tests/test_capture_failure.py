import json
import pytest
from carla_safety_agent.capture_failure import capture_failure

@pytest.mark.parametrize('patch',[{}, {'execution_id':'old'}, {'source':'other'}, {'error':None}, {'error':{}}, {'error':''}])
def test_only_exact_worker_failure_is_reported(tmp_path,patch):
    path=tmp_path/'status.json'
    row={'execution_id':'current','source':'sensor-rig','error':'write lock conflict','stop_reason':'capture_io_error'}
    row.update(patch);path.write_text(json.dumps(row))
    result=capture_failure(path,'current')
    assert (result is not None)==(not patch)
    if result:assert result=={'error':'write lock conflict','category':'capture_io_error'}

def test_missing_corrupt_and_oversized_are_not_attributed(tmp_path):
    path=tmp_path/'status.json'
    assert capture_failure(path,'current') is None
    for payload in ('{','x'*70000,'[]'):
        path.write_text(payload);assert capture_failure(path,'current') is None


@pytest.mark.parametrize('reason,category', [('quota_unknown','capture_quota_unknown'),
    ('capture_io_error','capture_io_error'), ('unexpected','capture_worker'), (None,'capture_worker'), ({},'capture_worker')])
def test_failure_category_uses_structured_marker_not_error_text(tmp_path, reason, category):
    path=tmp_path/'status.json'
    row={'execution_id':'current','source':'sensor-rig','error':'quota_unknown capture_io_error', 'stop_reason':reason}
    path.write_text(json.dumps(row))
    assert capture_failure(path,'current')['category']==category
    assert capture_failure(path,'different') is None


@pytest.mark.parametrize('configuration', ['invalid', '0', '-1', 'nan', '1.5'])
def test_real_quota_policy_stops_sample_before_write_and_preserves_reason(tmp_path, monkeypatch, configuration):
    from carla_safety_agent.capture_quota import capture_quota_policy, capture_write_lock
    from carla_safety_agent.sensor_capture import SensorCapture
    monkeypatch.setenv('CSA_CAPTURE_QUOTA_GIB', configuration)
    capture=object.__new__(SensorCapture)
    capture.run=tmp_path/'capture-test'
    capture.run.mkdir()
    capture.quota_policy=capture_quota_policy()
    assert capture.quota_policy['valid'] is False
    states=[]
    capture.manifest=lambda state:states.append(state)
    with capture_write_lock(tmp_path):
        capture._write_sample(1,{}, {}, {}, {}, 1)
    assert capture.run is None and capture.stop_reason=='quota_unknown'
    assert states==['saved_limit']
    assert not (tmp_path/'capture-test/samples').exists()
    status=tmp_path/'worker-status.json'
    status.write_text(json.dumps({'execution_id':'owned','source':'sensor-rig',
        'error':capture.error,'stop_reason':capture.stop_reason}))
    failure=capture_failure(status,'owned')
    assert failure['category']=='capture_quota_unknown'
    assert 'Invalid capture quota configuration' in failure['error']

import subprocess
from unittest.mock import patch

import pytest

from carla_safety_agent.capture_quality import audit_capture
from carla_safety_agent.data_quality import validate_capture_index


def test_index_identity_and_count():
    entries = [{'frame': 4, 'timestamp': 1., 'path': 'samples/0000000004'}]
    assert validate_capture_index(entries, {'frame_count': 1})['temporal_order_valid']
    for changed in ({'path': '../outside'}, {'timestamp': float('nan')}, {'frame': True}):
        with pytest.raises(ValueError):
            validate_capture_index([{**entries[0], **changed}], {'frame_count': 1})
    for count in (True, 0, 2, None):
        with pytest.raises(ValueError):
            validate_capture_index(entries, {'frame_count': count})


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

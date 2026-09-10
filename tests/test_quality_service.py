import json
from unittest.mock import patch

import pytest

from carla_safety_agent.quality_service import QualityService


def make_service(tmp_path, status='saved'):
    dataset = tmp_path / 'datasets' / 'capture-a'
    dataset.mkdir(parents=True)
    (dataset / 'manifest.json').write_text(json.dumps({
        'run_id':'capture-a', 'status':status, 'schema_version':'carla-safety-dataset/0.2'}))
    return QualityService(dataset.parent, tmp_path/'reports', '/tmp/check.py', '/usr/bin/python3'), dataset


def test_saved_report_survives_service_restart(tmp_path):
    service, path = make_service(tmp_path)
    assert service.status('capture-a')['state'] == 'not_checked'
    with patch('threading.Thread.start'):
        assert service.start('capture-a')['state'] == 'running'
        with pytest.raises(ValueError, match='already running'):
            service.start('capture-a')
    with patch('carla_safety_agent.quality_service.audit_capture', return_value={'state':'passed'}):
        service._scan('capture-a', path)
    assert service.active is None
    restarted = QualityService(service.datasets, service.reports, service.validator, service.python)
    assert restarted.status('capture-a')['state'] == 'passed'
    assert restarted.status('capture-a')['manifest_sha256']


def test_recording_and_escape_rejected(tmp_path):
    service, _ = make_service(tmp_path, 'recording')
    with pytest.raises(ValueError, match='saved'):
        service.start('capture-a')
    with pytest.raises(ValueError):
        service.start('../capture-a')


def test_recovered_capture_can_be_reaudited_but_pending_cannot(tmp_path):
    service,_=make_service(tmp_path,'saved_recovered')
    with patch('threading.Thread.start'):
        assert service.start('capture-a')['state']=='running'
    pending,_=make_service(tmp_path/'pending','recovery_pending')
    with pytest.raises(ValueError,match='saved'):pending.start('capture-a')


def test_changed_manifest_and_audit_failure_are_incomplete(tmp_path):
    service, path = make_service(tmp_path)
    def mutate(*args):
        (path/'manifest.json').write_text('{}')
        return {'state':'passed'}
    with patch('carla_safety_agent.quality_service.audit_capture', side_effect=mutate):
        service._scan('capture-a', path)
    assert service.status('capture-a')['state'] == 'incomplete'
    with patch('carla_safety_agent.quality_service.audit_capture', side_effect=RuntimeError('disk error')):
        service._scan('capture-a', path)
    assert service.active is None
    assert service.status('capture-a')['state'] == 'incomplete'

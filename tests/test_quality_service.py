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


def test_interrupted_scan_does_not_resurface_previous_pass(tmp_path):
    service, path = make_service(tmp_path)
    with patch('carla_safety_agent.quality_service.audit_capture', return_value={'state':'passed'}):
        service._scan('capture-a', path)
    old = json.loads(service._report_path('capture-a').read_text())
    with patch('threading.Thread.start'):
        service.start('capture-a')
    restarted = QualityService(service.datasets, service.reports, service.validator, service.python)
    pending = service._report_path('capture-a').read_bytes()
    status = restarted.status('capture-a')
    assert status['state'] == 'incomplete'
    assert status['reason_code'] == 'validation_interrupted'
    assert service._report_path('capture-a').read_bytes() == pending
    assert [json.loads(p.read_text()) for p in (service.reports/'history').glob('*.json')] == [old]


def test_quality_start_write_failure_never_starts_worker(tmp_path):
    service, _ = make_service(tmp_path)
    with patch('carla_safety_agent.quality_service.durable_write', side_effect=OSError('disk full')):
        with patch('threading.Thread.start') as launch:
            with pytest.raises(OSError): service.start('capture-a')
            launch.assert_not_called()
    assert service.active is None and not service.transient
    assert service._lease is None


def test_separate_quality_instances_cannot_overwrite_running_report(tmp_path):
    service, path = make_service(tmp_path)
    peer = QualityService(service.datasets, service.reports, service.validator, service.python)
    with patch('threading.Thread.start'):
        service.start('capture-a')
        before = service._report_path('capture-a').read_bytes()
        with pytest.raises(ValueError, match='scan lock'):
            peer.start('capture-a')
        assert service._report_path('capture-a').read_bytes() == before
        assert peer.active is None and peer._lease is None
    with patch('carla_safety_agent.quality_service.audit_capture', return_value={'state':'passed'}) as audit:
        service._scan('capture-a', path)
        assert len(audit.call_args.kwargs['pass_fds']) == 1
    assert service._lease is None
    with patch('threading.Thread.start'):
        peer.start('capture-a')
    with patch('carla_safety_agent.quality_service.audit_capture', return_value={'state':'passed'}):
        peer._scan('capture-a', path)


def test_inherited_scan_lock_blocks_peer_until_real_child_exits(tmp_path):
    import subprocess
    import sys
    service, path = make_service(tmp_path)
    peer = QualityService(service.datasets, service.reports, service.validator, service.python)
    child = None
    try:
        with patch('threading.Thread.start'):
            service.start('capture-a')
        child = subprocess.Popen([sys.executable, '-c', 'import sys; sys.stdin.read()'],
            stdin=subprocess.PIPE, pass_fds=(service._lease.fileno(),))
        service._lease.close()
        service._lease = None
        saved = service._report_path('capture-a').read_bytes()
        assert child.poll() is None
        with pytest.raises(ValueError, match='scan lock'):
            peer.start('capture-a')
        assert service._report_path('capture-a').read_bytes() == saved
        child.communicate(timeout=5)
        assert child.returncode == 0
        with patch('threading.Thread.start'):
            assert peer.start('capture-a')['state'] == 'running'
        with patch('carla_safety_agent.quality_service.audit_capture', return_value={'state':'passed'}):
            peer._scan('capture-a', path)
        assert peer._lease is None
    finally:
        if child is not None and child.poll() is None:
            child.terminate()
            child.wait(timeout=5)
        if service._lease is not None:
            service._lease.close()
        if peer._lease is not None:
            peer._lease.close()


def test_previous_instance_reads_newer_durable_quality_result(tmp_path):
    service, path = make_service(tmp_path)
    peer = QualityService(service.datasets, service.reports, service.validator, service.python)
    with patch('carla_safety_agent.quality_service.audit_capture', return_value={'state':'passed'}):
        service._scan('capture-a', path)
    assert service.status('capture-a')['state'] == 'passed'
    with patch('threading.Thread.start'):
        peer.start('capture-a')
    # Not owned here: report unknown completion, never the older passed result.
    assert service.status('capture-a')['state'] == 'incomplete'
    with patch('carla_safety_agent.quality_service.audit_capture', return_value={
            'state':'failed', 'reason_code':'invalid_ego_pose', 'problem_frame':42}):
        peer._scan('capture-a', path)
    status = service.status('capture-a')
    assert status['state'] == 'failed' and status['problem_frame'] == 42
    assert service.transient == {} and peer.transient == {}


@pytest.mark.parametrize('restarted', [False, True])
def test_status_detects_changed_manifest_without_rewriting_report(tmp_path, restarted):
    service, path = make_service(tmp_path)
    with patch('carla_safety_agent.quality_service.audit_capture', return_value={'state':'passed'}):
        service._scan('capture-a', path)
    report_path = service._report_path('capture-a')
    before = report_path.read_bytes()
    if restarted:
        service = QualityService(service.datasets, service.reports, service.validator, service.python)
    assert service.status('capture-a')['manifest_freshness'] == 'unchanged'
    (path / 'manifest.json').write_text('{}')
    observed = service.status('capture-a')
    assert observed['manifest_freshness'] == 'changed'
    assert observed['state'] == 'passed'  # Historical evidence is not rewritten.
    assert report_path.read_bytes() == before


@pytest.mark.parametrize('status', ['saved_recovered', 'saved_capture_error', 'saved_cleanup_error'])
def test_recovered_capture_can_be_reaudited_but_pending_cannot(tmp_path,status):
    service,_=make_service(tmp_path,status)
    with patch('threading.Thread.start'):
        assert service.start('capture-a')['state']=='running'
    pending,_=make_service(tmp_path/'pending','recovery_pending')
    with pytest.raises(ValueError,match='saved'):pending.start('capture-a')


def test_failed_capture_can_be_diagnosed_without_rewriting_capture_status(tmp_path):
    import sys
    from pathlib import Path
    service, path = make_service(tmp_path, 'saved_capture_error')
    manifest_path = path / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    manifest.update(frame_count=0, input_archive='sensor_input.npz', error='sensor write failed')
    manifest_path.write_text(json.dumps(manifest))
    (path / 'index.json').write_text(json.dumps({'frames': []}))
    (path / 'calibration.json').write_text('{}')
    before = manifest_path.read_bytes()
    service.validator = Path(__file__).resolve().parents[1] / 'tools/validate_capture_dataset.py'
    service.python = sys.executable
    with patch('threading.Thread.start'):
        assert service.start('capture-a')['state'] == 'running'
    service._scan('capture-a', path)
    report = service.status('capture-a')
    assert report['state'] == 'failed' and report['reason_code'] == 'no_samples'
    assert service.active is None
    assert manifest_path.read_bytes() == before


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

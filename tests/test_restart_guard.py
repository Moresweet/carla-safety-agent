import pytest
from carla_safety_agent.restart_guard import verify_idle


@pytest.mark.parametrize('status', [None, {}, {'schema_version': 'asset-restart/1', 'unresolved': None}])
def test_asset_restart_unknown_refused(status):
    from carla_safety_agent.restart_guard import verify_asset_jobs_idle
    with pytest.raises(ValueError, match='unknown'):
        verify_asset_jobs_idle(status)


def test_asset_restart_unresolved_refused():
    from carla_safety_agent.restart_guard import verify_asset_jobs_idle
    verify_asset_jobs_idle({'schema_version': 'asset-restart/1', 'unresolved': []})
    for state in ('preparing', 'generating', 'importing', 'needs_attention'):
        with pytest.raises(ValueError, match='unresolved'):
            verify_asset_jobs_idle({'schema_version': 'asset-restart/1', 'unresolved': [{'state': state}]})


@pytest.mark.parametrize('mode', ['--stop', '--after-crash-stop', '--resume-recovery'])
def test_restart_script_never_signals_unrelated_same_directory_process(tmp_path, mode):
    import subprocess
    import sys
    from pathlib import Path
    source = Path(__file__).resolve().parents[1] / 'scripts/restart_studio_bridge.sh'
    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    (scripts / 'restart_studio_bridge.sh').write_bytes(source.read_bytes())
    (scripts / 'studio_paths.sh').write_text('# isolated fixture\n')
    (tmp_path / '.runtime').mkdir()
    # Same cwd and a deceptive matching argument: the old substring check passed.
    child = subprocess.Popen([sys.executable, '-c', 'import sys; sys.stdin.read()',
                              'tools/livery_bridge.py'], cwd=tmp_path, stdin=subprocess.PIPE)
    try:
        (tmp_path / '.runtime/bridge.pid').write_text(str(child.pid))
        result = subprocess.run(['bash', str(scripts / 'restart_studio_bridge.sh'), mode],
                                cwd=tmp_path, capture_output=True, text=True, timeout=10)
        assert result.returncode != 0
        assert 'Bridge command identity mismatch' in result.stderr
        assert child.poll() is None
        assert not (tmp_path / '.runtime/bridge.log').exists()
        child.communicate(timeout=5)
        assert child.returncode == 0
    finally:
        if child.poll() is None:
            child.terminate()
            child.wait(timeout=5)


@pytest.mark.parametrize('job',['recovery','excerpt','quality','archive'])
def test_dataset_worker_blocks_restart(job):
    from carla_safety_agent.restart_guard import verify_dataset_jobs_idle
    status={'schema_version':'dataset-jobs/1','active':dict.fromkeys(['recovery','excerpt','quality','archive'])}
    verify_dataset_jobs_idle(status)
    status['active'][job]='running-id'
    with pytest.raises(ValueError,match='active'):verify_dataset_jobs_idle(status)


@pytest.mark.parametrize('status',[None,{}, {'schema_version':'dataset-jobs/1','active':{}}])
def test_missing_dataset_status_refuses_restart(status):
    from carla_safety_agent.restart_guard import verify_dataset_jobs_idle
    with pytest.raises(ValueError,match='unknown'):verify_dataset_jobs_idle(status)


@pytest.mark.parametrize('state',['running','needs_attention','unknown',None])
def test_routine_restart_refuses_pending_map_handoff(state):
    from carla_safety_agent.restart_guard import verify_handoff_idle
    with pytest.raises(ValueError):verify_handoff_idle({'state':state})
    verify_handoff_idle({'state':'restored'})


@pytest.mark.parametrize('scheduler', [{'state': 'running'}, {}, None])
def test_restart_refuses_scheduler_even_between_simulations(scheduler):
    with pytest.raises(ValueError, match='scheduler'):
        verify_idle({'state': 'completed'}, scheduler)


def test_restart_requires_terminal_session_and_dead_owned_process():
    scheduler = {'state': 'completed'}
    with pytest.raises(ValueError):
        verify_idle({'state': 'running'}, scheduler)
    identity = {'pid': 42, 'start_ticks': '100'}
    session = {'state': 'completed', 'process': identity}
    with pytest.raises(ValueError, match='still alive'):
        verify_idle(session, scheduler, lambda pid: identity)
    verify_idle(session, scheduler, lambda pid: None)
    verify_idle(session, scheduler, lambda pid: {'pid': 42, 'start_ticks': '200'})
    with pytest.raises(PermissionError):
        def denied(pid):
            raise PermissionError('Cannot inspect process')
        verify_idle(session, scheduler, denied)


def test_asset_endpoint_legacy_fallback_requires_explicit_404():
    from urllib.error import HTTPError
    from carla_safety_agent.restart_guard import verify_asset_endpoint
    calls = []
    def local():
        calls.append('local')
        return {'schema_version': 'asset-restart/1', 'unresolved': []}
    def missing(path):
        assert path == 'blender/restart-status'
        raise HTTPError(path, 404, 'missing', {}, None)
    with pytest.raises(HTTPError):
        verify_asset_endpoint(missing, local)
    assert calls == []
    verify_asset_endpoint(missing, local, legacy_upgrade=True)
    assert calls == ['local']
    for error in [HTTPError('endpoint', 500, 'failure', {}, None), TimeoutError('timeout')]:
        def failed(path):
            raise error
        with pytest.raises(type(error)):
            verify_asset_endpoint(failed, local, legacy_upgrade=True)
    assert calls == ['local']
    with pytest.raises(ValueError):
        verify_asset_endpoint(missing, lambda: {'schema_version': 'asset-restart/1',
            'unresolved': ['pending']}, legacy_upgrade=True)
    with pytest.raises(ValueError):
        verify_asset_endpoint(missing, lambda: {}, legacy_upgrade=True)
    verify_asset_endpoint(lambda path: local(),
        lambda: pytest.fail('Healthy endpoint must not use local fallback'), legacy_upgrade=True)


def test_restart_script_refuses_live_native_import_lock(tmp_path):
    import fcntl
    import subprocess
    from pathlib import Path
    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    source = Path(__file__).resolve().parents[1] / 'scripts/restart_studio_bridge.sh'
    script = scripts / source.name
    script.write_bytes(source.read_bytes())
    (scripts / 'studio_paths.sh').write_text('# isolated test\n')
    assets = tmp_path / '.runtime/blender-assets'
    assets.mkdir(parents=True)
    with (assets / 'import.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = subprocess.run(['bash', str(script), '--upgrade-legacy-assets'],
            cwd=tmp_path, capture_output=True, text=True, timeout=10)
        assert result.returncode != 0
        assert 'Native asset import active' in result.stderr
        assert not (tmp_path / '.runtime/bridge.pid').exists()
        assert not (tmp_path / '.runtime/bridge.log').exists()


def test_legacy_health_requires_explicit_mode_and_both_probes():
    from carla_safety_agent.restart_guard import verify_asset_endpoint
    health = {'ok': True, 'service': 'carla-surface-bridge'}
    calls = []
    def fetch(path):
        calls.append(path)
        return health
    def local():
        calls.append('local')
        return {'schema_version': 'asset-restart/1', 'unresolved': []}
    with pytest.raises(ValueError):
        verify_asset_endpoint(fetch, local)
    assert calls == ['blender/restart-status']
    calls.clear()
    verify_asset_endpoint(fetch, local, legacy_upgrade=True)
    assert calls[:2] == ['blender/restart-status', '']
    assert calls[2].startswith('__legacy_probe_')
    assert calls[3:] == ['local']
    for bad_route in ('root', 'probe'):
        def mismatch(path):
            if (bad_route == 'root' and path == '') or (bad_route == 'probe' and path.startswith('__legacy_probe_')):
                return {'ok': True}
            return health
        with pytest.raises(ValueError, match='fingerprint'):
            verify_asset_endpoint(mismatch, lambda: pytest.fail('No fallback for mismatched bridge'), legacy_upgrade=True)
    with pytest.raises(ValueError, match='unresolved'):
        verify_asset_endpoint(fetch, lambda: {'schema_version': 'asset-restart/1',
            'unresolved': ['running']}, legacy_upgrade=True)

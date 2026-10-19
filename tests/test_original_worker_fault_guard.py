import importlib.util
from pathlib import Path

import pytest


@pytest.mark.parametrize('current_owner,should_stop', [('owned', True), ('new-owner', False)])
def test_real_sigterm_runs_main_cleanup_without_stopping_another_task(tmp_path, current_owner, should_stop):
    """Real OS signal and main(), fake HTTP/CARLA; never launch a simulator."""
    import json
    import selectors
    import signal
    import subprocess
    import sys
    tools = Path(__file__).resolve().parents[1] / 'tools'
    child = r'''
import sys, signal, types
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import regression_worker_crash_recovery as probe
probe.ROOT = Path(sys.argv[2])
current_owner = sys.argv[3]
sys.argv = ['probe']
sys.modules['carla'] = types.SimpleNamespace()
observed = False
def request(route, payload=None):
    global observed
    if route == '/system/preflight': return {'ready': True}
    if route == '/batches/scheduler': return {'scheduler': {'state': 'idle'}}
    if route == '/scenario/compile': return {'scenario_path': 'plan', 'scenario_sha256': 'hash'}
    if route == '/scenario/execute-plan': return {'execution_id': 'owned'}
    if route == '/session/status':
        if not observed:
            observed = True
            print('SIGNAL_READY', flush=True)
            signal.pause()
            raise AssertionError('Expected SIGTERM to unwind')
        return {'session': {'run_id': current_owner, 'state': 'running'}}
    if route == '/e2e/stop':
        assert payload == {'run_id': 'owned'}
        print('OWNED_STOP_REQUESTED', flush=True)
        return {'state': 'stopping'}
    raise AssertionError(route)
probe.request = request
probe.main()
'''
    process = subprocess.Popen([sys.executable, '-u', '-c', child, str(tools), str(tmp_path), current_owner],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        # The initial report precedes the readiness line; use an OS-level
        # bounded read to avoid indefinite waits if the child fails early.
        import os
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        import time
        deadline = time.monotonic() + 10
        output = b''
        while b'SIGNAL_READY\n' not in output and time.monotonic() < deadline:
            if selector.select(timeout=.2):
                chunk = os.read(process.stdout.fileno(), 4096)
                if not chunk: break
                output += chunk
        selector.close()
        assert b'SIGNAL_READY\n' in output, output
        process.send_signal(signal.SIGTERM)
        stdout, stderr = process.communicate(timeout=10)
        assert process.returncode == 143, stderr
        assert ('OWNED_STOP_REQUESTED' in stdout) is should_stop
        report = json.loads(next((tmp_path/'runs/validation').glob('*.json')).read_text())
        assert report['state'] == 'failed' and report['error'] == '143'
        assert report['execution_id'] == 'owned'
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_observer_sigterm_unwinds_for_owned_task_cleanup(monkeypatch):
    import signal
    tools = Path(__file__).resolve().parents[1] / 'tools'
    monkeypatch.syspath_prepend(str(tools))
    spec = importlib.util.spec_from_file_location('fault_probe_term', tools/'regression_worker_crash_recovery.py')
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)
    with pytest.raises(SystemExit) as failure:
        probe.interrupted_observer(signal.SIGTERM, None)
    assert failure.value.code == 143


@pytest.mark.parametrize('mismatch', [None, 'command', 'algorithm', 'route', 'hash', 'execution', 'model', 'status'])
def test_original_fault_injection_refuses_identity_mismatch(monkeypatch, mismatch):
    tools = Path(__file__).resolve().parents[1] / 'tools'
    monkeypatch.syspath_prepend(str(tools))
    spec = importlib.util.spec_from_file_location('fault_probe', tools/'regression_worker_crash_recovery.py')
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)
    command = ['python', str(probe.ROOT/'tools/run_opendrive_native.py')]
    session = {'run_id': 'owned', 'configuration': {'command': command.copy(),
        'request': {'algorithm': 'driveadapter', 'route': 'plan.json'}, 'scenario_sha256': 'hash'}}
    plan = {'scenario_path': 'plan.json', 'scenario_sha256': 'hash'}
    manifest = {'execution_id': 'owned', 'model': 'driveadapter-experimental', 'status': 'recording'}
    if mismatch == 'command': command[1] = '/unrelated/worker.py'
    if mismatch in ('algorithm', 'route'): session['configuration']['request'][mismatch] = 'other'
    if mismatch == 'hash': session['configuration']['scenario_sha256'] = 'other'
    if mismatch == 'execution': manifest['execution_id'] = 'other'
    if mismatch == 'model': manifest['model'] = 'thinktwice-experimental'
    if mismatch == 'status': manifest['status'] = 'saved'
    if mismatch:
        with pytest.raises(AssertionError):
            probe.require_original_worker([c.encode() for c in command], session, plan, 'driveadapter', manifest)
    else:
        probe.require_original_worker([c.encode() for c in command], session, plan, 'driveadapter', manifest)

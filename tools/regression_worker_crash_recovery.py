"""Opt-in SIGKILL of this tool's own AD-MLP task; verify durable actor recovery."""
import json
import os
from pathlib import Path
import re
import signal
import time
import uuid

import carla

from carla_safety_agent.owned_resources import read_resources, resource_path
from carla_safety_agent.session import observed_process_identity
from carla_safety_agent.world_health import observe_idle
from regression_material_slots import ROOT, request


def main():
    assert request('/system/preflight')['ready']
    assert request('/batches/scheduler')['scheduler']['state'] != 'running'
    plan = request('/scenario/compile', {'description': 'Town04 前车急刹，自车 5 m/s', 'max_duration_s': 10})
    result = request('/scenario/execute-plan', {'confirmed': True, 'scenario_path': plan['scenario_path'],
        'scenario_sha256': plan['scenario_sha256'], 'algorithm': 'admlp', 'unified_capture': True})
    execution = result['execution_id']
    output = ROOT/'runs/validation'/('worker-crash-recovery-'+uuid.uuid4().hex+'.json')
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {'execution_id': execution, 'state': 'waiting', 'scope': 'Owned native worker SIGKILL; not server crash'}
    output.write_text(json.dumps(report, indent=2))
    try:
        deadline = time.monotonic()+300
        while time.monotonic() < deadline:
            session = request('/session/status')['session']
            assert session['run_id'] == execution, 'Execution ownership changed'
            assert session['state'] in ('preparing', 'running'), session
            path = resource_path(ROOT/'data', execution)
            if path.exists() and session.get('process'):
                document = read_resources(path, session)
                capture = request('/capture/status').get('capture') or {}
                if len(document['actors']) >= 10 and capture.get('recording') and capture.get('recorded_frames', 0) >= 5:
                    run_id = capture.get('run_id')
                    if not isinstance(run_id, str) or not re.fullmatch(r'capture-[A-Za-z0-9_-]+', run_id):
                        raise ValueError('Invalid capture identity')
                    manifest_path = ROOT/'.runtime/generated-scenarios'/str(run_id)/'manifest.json'
                    if manifest_path.exists() and json.loads(manifest_path.read_text()).get('execution_id') == execution:
                        break
            time.sleep(.2)
        else:
            raise TimeoutError('Owned worker did not reach a captured frame')
        owner = session['process']
        pid = owner['pid']
        assert observed_process_identity(pid) == owner, 'Worker identity changed'
        command = Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
        assert b'carla_safety_agent.native_executor' in command, 'Not our native worker'
        assert command[command.index(b'--scenario')+1] == os.fsencode(plan['scenario_path'])
        assert command[command.index(b'--agent')+1] == os.fsencode(ROOT/'integration/bench2drive/admlp_agent.py')
        assert session['configuration']['command'] == [str(ROOT/'scripts/run_benchmark_preset.sh')]
        latest = request('/session/status')['session']
        assert latest['run_id'] == execution and latest['process'] == owner and latest['state'] == 'running'
        assert observed_process_identity(pid) == owner
        report.update(state='injecting_sigkill', process=owner, actors=document['actors'], dataset=run_id,
                      worker_cwd=str(Path(f'/proc/{pid}/cwd').resolve()))
        output.write_text(json.dumps(report, indent=2))
        os.kill(pid, signal.SIGKILL)
        deadline = time.monotonic()+120
        while time.monotonic() < deadline:
            session = request('/session/status')['session']
            assert session['run_id'] == execution
            if session['state'] == 'failed': break
            if session['state'] == 'recovering' and session.get('error'):
                raise RuntimeError(f"Recovery needs attention: {session['error']}")
            time.sleep(.5)
        else: raise TimeoutError('Worker crash recovery did not finish')
        assert session['returncode'] == -signal.SIGKILL, session
        recovered = read_resources(path, session)
        assert recovered['state'] == 'recovered'
        client = carla.Client('127.0.0.1', 2000)
        client.set_timeout(10)
        health = observe_idle(client, document['map'])
        assert health['episode'] == document['episode']
        existing = {actor.id for actor in client.get_world().get_actors()}
        assert not existing.intersection(row['id'] for row in document['actors'])
        assert request('/system/preflight')['ready']
        report.update(state='verified', session=session, post_exit_health=health)
        output.write_text(json.dumps(report, indent=2))
        print(output, flush=True)
    except BaseException as exc:
        report.update(state='failed', error=str(exc))
        output.write_text(json.dumps(report, indent=2))
        current = request('/session/status')['session']
        if current['run_id'] == execution and current['state'] in ('preparing', 'running', 'stopping'):
            request('/e2e/stop', {'run_id': execution})
        raise


if __name__ == '__main__':
    main()

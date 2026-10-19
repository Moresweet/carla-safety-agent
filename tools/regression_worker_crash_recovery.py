"""Opt-in SIGKILL of this tool's own worker; verify durable actor recovery."""
import json
import argparse
import os
from pathlib import Path
import re
import signal
import time
import uuid

from carla_safety_agent.owned_resources import read_resources, resource_path
from carla_safety_agent.session import observed_process_identity
from carla_safety_agent.world_health import observe_idle
from regression_material_slots import ROOT, request


def require_original_worker(command, session, plan, model, manifest):
    """Independent identity gates in addition to PID/start-time verification."""
    assert os.fsencode(ROOT/'tools/run_opendrive_native.py') in command, 'Not our original model worker'
    assert [os.fsdecode(item) for item in command if item] == session['configuration']['command']
    assert session['configuration']['request']['algorithm'] == model
    assert session['configuration']['request']['route'] == plan['scenario_path']
    assert session['configuration']['scenario_sha256'] == plan['scenario_sha256']
    assert manifest['execution_id'] == session['run_id']
    assert manifest['model'] == model + '-experimental'
    assert manifest['status'] == 'recording'


def interrupted_observer(signum, frame):
    # Default SIGTERM bypasses the exception cleanup below and leaves a live
    # test worker behind. Unwind normally so its exact execution can be stopped.
    raise SystemExit(128 + signum)


def main():
    if not __debug__:
        raise RuntimeError('Fault acceptance requires assertions; do not use Python -O')
    import carla
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sensor-rig-mode', choices=('stationary', 'manual', 'autopilot'))
    parser.add_argument('--rule-run', action='store_true')
    parser.add_argument('--original-model', choices=('thinktwice', 'driveadapter'))
    args = parser.parse_args()
    if sum(bool(value) for value in (args.rule_run, args.sensor_rig_mode, args.original_model)) > 1:
        parser.error('Choose one worker type')
    if args.original_model:
        from carla_safety_agent.acceptance_storage import require_original_capture_space
        require_original_capture_space(ROOT)
    assert request('/system/preflight')['ready']
    assert request('/batches/scheduler')['scheduler']['state'] != 'running'
    if args.original_model:
        saved = request('/scenes/save', {'name': args.original_model + ' 故障验收前快照'})
        assert not saved['document']['objects'], 'Test requires no user-owned dynamic objects'
        town = saved['document']['map'].split('/')[-1]
        plan = request('/scenario/compile', {'description': f'{town} 前车急刹，自车 5 m/s', 'max_duration_s': 4})
        result = request('/scenario/execute-plan', {'confirmed': True, 'scenario_path': plan['scenario_path'],
            'scenario_sha256': plan['scenario_sha256'], 'algorithm': args.original_model, 'unified_capture': True})
        execution = result['execution_id']
    elif args.sensor_rig_mode:
        result = request('/e2e/start', {'action': 'sensor-rig', 'mode': args.sensor_rig_mode,
                                      'frames': 1000, 'every': 1})
        execution = request('/session/status')['session']['run_id']
    elif args.rule_run:
        plan = request('/scenario/compile', {'description': 'Town04 前车急刹，自车 5 m/s', 'max_duration_s': 20})
        result = request('/e2e/start', {'action':'rule-run','route':plan['scenario_path'],
            'scenario_sha256':plan['scenario_sha256'],'unified_capture':True})
        execution = request('/session/status')['session']['run_id']
    else:
        plan = request('/scenario/compile', {'description': 'Town04 前车急刹，自车 5 m/s', 'max_duration_s': 10})
        result = request('/scenario/execute-plan', {'confirmed': True, 'scenario_path': plan['scenario_path'],
            'scenario_sha256': plan['scenario_sha256'], 'algorithm': 'admlp', 'unified_capture': True})
        execution = result['execution_id']
    output = ROOT/'runs/validation'/('worker-crash-recovery-'+uuid.uuid4().hex+'.json')
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {'execution_id': execution, 'state': 'waiting', 'scope': 'Owned native worker SIGKILL; not server crash'}
    report['original_model'] = args.original_model
    output.write_text(json.dumps(report, indent=2))
    print(json.dumps({'report': str(output), 'execution_id': execution}), flush=True)
    previous_term_handler = signal.signal(signal.SIGTERM, interrupted_observer)
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
                if len(document['actors']) >= 10 and capture.get('recording') and capture.get('recorded_frames', 0) >= (40 if args.original_model else 5):
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
        if args.sensor_rig_mode=='autopilot' or args.rule_run:
            assert document.get('traffic_manager',{}).get('port')==(8051 if args.rule_run else 8050), 'Traffic Manager ownership was not recorded'
        pid = owner['pid']
        assert observed_process_identity(pid) == owner, 'Worker identity changed'
        command = Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
        if args.original_model:
            manifest_before = json.loads(manifest_path.read_text())
            require_original_worker(command, session, plan, args.original_model, manifest_before)
        elif args.sensor_rig_mode:
            assert os.fsencode(ROOT/'tools/run_sensor_rig.py') in command, 'Not our capture worker'
            assert command[command.index(b'--mode')+1] == os.fsencode(args.sensor_rig_mode)
            assert session['kind'] == 'sensor-rig' and session['configuration']['request']['mode'] == args.sensor_rig_mode
            assert [os.fsdecode(item) for item in command if item] == session['configuration']['command']
        elif args.rule_run:
            assert os.fsencode(ROOT/'tools/run_rule_scenario.py') in command, 'Not our rule worker'
            assert [os.fsdecode(item) for item in command if item] == session['configuration']['command']
            assert session['kind']=='rule-run'
            assert session['configuration']['request']['route']==plan['scenario_path']
            assert session['configuration']['scenario_sha256']==plan['scenario_sha256']
        else:
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
        assert session['outcome']['execution'] == 'failed', session
        assert session['outcome']['failure_category'] == 'process_exit', session
        assert session['outcome']['result_assessed'] is False, session
        recovered = read_resources(path, session)
        assert recovered['state'] == 'recovered'
        if args.sensor_rig_mode=='autopilot' or args.rule_run:
            from carla_safety_agent.traffic_manager_ownership import require_stopped_manager
            require_stopped_manager(recovered['traffic_manager'])
        client = carla.Client('127.0.0.1', 2000)
        client.set_timeout(10)
        health = observe_idle(client, document['map'])
        assert health['episode'] == document['episode']
        existing = {actor.id for actor in client.get_world().get_actors()}
        assert not existing.intersection(row['id'] for row in document['actors'])
        assert request('/system/preflight')['ready']
        if args.original_model:
            # Abrupt death bypasses finalization. Never relabel this capture as
            # saved; recovery must be an explicit, separately verified copy.
            interrupted = json.loads(manifest_path.read_text())
            assert interrupted['execution_id'] == execution
            assert interrupted['status'] == 'recording', interrupted
            report['interrupted_capture'] = {'status': interrupted['status'],
                'frames': interrupted['frame_count'], 'requires_explicit_recovery': True}
        report.update(state='verified', session=session, post_exit_health=health)
        output.write_text(json.dumps(report, indent=2))
        print(output, flush=True)
    except BaseException as exc:
        report.update(state='failed', error=str(exc))
        output.write_text(json.dumps(report, indent=2))
        current = request('/session/status')['session']
        if current['run_id'] == execution and current['state'] in ('preparing', 'running', 'stopping'):
            request('/collection/stop' if args.sensor_rig_mode else '/e2e/stop', {'run_id': execution})
        raise
    finally:
        signal.signal(signal.SIGTERM, previous_term_handler)


if __name__ == '__main__':
    main()

"""Explicit experimental same-map run through the existing session owner."""
import json
import time
import uuid
import subprocess
import sys
import os
import argparse
from regression_scene_versions import ROOT, request


def complete_capture_verified(datasets):
    return bool(datasets) and all(
        d['valid'] and d['prediction_valid'] and d['frames'] == 80 and d['status'] == 'saved'
        and not d['error'] and not d['stop_reason'] for d in datasets)


def cancelled_capture_verified(datasets):
    # A partial recording must contain actual predictions, be finalized and
    # remain distinct from the complete 80-frame acceptance case.
    return len(datasets) == 1 and all(
        d['valid'] and d['prediction_valid'] and 40 <= d['frames'] < 80
        and d['status'] == 'saved' and not d['error'] and not d['stop_reason']
        for d in datasets)


def main():
    if not __debug__:
        raise RuntimeError('Acceptance requires assertions; do not use Python -O')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', choices=('thinktwice', 'driveadapter'), default='thinktwice')
    cancel_modes = parser.add_mutually_exclusive_group()
    cancel_modes.add_argument('--cancel-after-inference', action='store_true',
                        help='Stop after at least 32 completed steps; no dataset recording')
    cancel_modes.add_argument('--cancel-with-capture', action='store_true',
                        help='Stop during recording after at least 40 completed steps; validate saved partial data')
    args = parser.parse_args()
    cancel = args.cancel_after_inference or args.cancel_with_capture
    storage = None
    if not args.cancel_after_inference:
        from carla_safety_agent.acceptance_storage import require_original_capture_space
        storage = require_original_capture_space(ROOT)
    assert request('system/preflight')['ready']
    assert request('batches/scheduler')['scheduler']['state'] != 'running'
    output = ROOT/'runs/validation'/(args.model+'-native-'+uuid.uuid4().hex+'.json')
    report = {'ok': False, 'scope': 'Four-second experimental real-sensor run, not driving quality certification'}
    report['mode'] = ('cancel_with_capture' if args.cancel_with_capture else
                      'cancel_after_inference' if args.cancel_after_inference else 'complete_with_capture')
    report['storage_admission'] = storage
    def save():
        output.write_text(json.dumps(report, indent=2))
    saved = request('scenes/save', {'name': args.model + ' 原生验收前快照'})
    document = saved['document']
    assert not document['objects'], 'Test requires no user-owned dynamic objects'
    town = document['map'].split('/')[-1]
    report.update(saved_scene=saved['head']['scene_id'], map=town)
    save()
    plan = request('scenario/compile', {'description': f'{town} 前车急刹，自车 5 m/s', 'max_duration_s': 4})
    response = request('scenario/execute-plan', {'confirmed': True, 'scenario_path': plan['scenario_path'],
        'scenario_sha256': plan['scenario_sha256'], 'algorithm': args.model,
        'unified_capture': not args.cancel_after_inference})
    report['execution_id'] = response['execution_id']
    save()
    print(json.dumps({'report': str(output), 'execution_id': report['execution_id']}), flush=True)
    previous = None
    while True:
        state = request('session/status')
        session = state['session']
        assert session['run_id'] == report['execution_id'], 'Session ownership changed'
        phase = (session['state'], state.get('progress', {}).get('phase'))
        if phase != previous:
            print(json.dumps({'state': phase}), flush=True)
            previous = phase
        progress = state.get('progress', {})
        if (cancel and not report.get('stop_requested')
                and session['state'] == 'running' and progress.get('phase') == 'inference'
                and (progress.get('completed_steps') or 0) >= (40 if args.cancel_with_capture else 32)):
            # Keep exact execution identity; never stop whichever task happens
            # to be current after an ownership change.
            report['stop_progress'] = progress
            report['stop_requested'] = True
            save()
            report['stop_response'] = request('e2e/stop', {'run_id': report['execution_id']})
            save()
        if session['state'] not in ('preparing', 'running', 'stopping', 'recovering'):
            report['session'] = session
            report['execution_ok'] = session['state'] == 'completed' and session.get('returncode') == 0
            save()
            if cancel:
                assert report.get('stop_requested'), 'Task exited before inference cancellation'
                assert session['state'] == 'stopped', session
                assert session.get('returncode') == 130, session
                outcome = session.get('outcome', {})
                assert outcome.get('result_assessed') is False, outcome
                assert outcome.get('benchmark_failed') is False, outcome
                assert outcome.get('failure_category') is None, outcome
            if args.cancel_after_inference:
                import carla
                from carla_safety_agent.world_health import observe_idle
                client = carla.Client('127.0.0.1', 2000)
                client.set_timeout(15)
                report['post_exit_world'] = observe_idle(client, town)
                report['ok'] = True
                save()
                print(json.dumps({'ok': True, 'report': str(output)}), flush=True)
                return 0
            if report['execution_ok'] or args.cancel_with_capture:
                datasets = []
                for manifest in (ROOT/'.runtime/generated-scenarios').glob('capture-*/manifest.json'):
                    data = json.loads(manifest.read_text())
                    if data.get('execution_id') != report['execution_id']:
                        continue
                    result = subprocess.run([sys.executable, str(ROOT/'tools/validate_capture_dataset.py'),
                                             str(manifest.parent)], capture_output=True, text=True,
                                            env={**os.environ, 'PYTHONPATH': os.pathsep.join((str(ROOT/'src'),os.environ.get('PYTHONPATH','')))})
                    prediction = subprocess.run(
                        [sys.executable, str(ROOT/'tools/validate_thinktwice_prediction.py'),
                         str(manifest.parent), '--model', args.model,
                         *(['--require-map-projection'] if args.model=='driveadapter' else [])], capture_output=True, text=True,
                        env={**os.environ, 'PYTHONPATH': os.pathsep.join((str(ROOT/'src'),os.environ.get('PYTHONPATH','')))})
                    datasets.append({'path': str(manifest.parent), 'frames': data['frame_count'],
                                     'status': data.get('status'), 'error': data.get('error'),
                                     'stop_reason': data.get('stop_reason'),
                                     'valid': result.returncode == 0,
                                     'prediction_valid': prediction.returncode == 0,
                                     'prediction_validation': prediction.stdout + prediction.stderr,
                                     'validation': result.stdout + result.stderr})
                report['datasets'] = datasets
                # Successful process exit and complete files do not prove that
                # the simulator was released. Apply the same real-world gate
                # used by cancellation acceptance before calling this a pass.
                report['capture_ok'] = (cancelled_capture_verified(datasets) if args.cancel_with_capture
                                        else complete_capture_verified(datasets))
                save()
                import carla
                from carla_safety_agent.world_health import observe_idle
                client = carla.Client('127.0.0.1', 2000)
                client.set_timeout(15)
                try:
                    report['post_exit_world'] = observe_idle(client, town)
                except Exception as error:
                    report['cleanup_error'] = str(error)
                    save()
                    raise
                report['ok'] = report['capture_ok']
                save()
            print(json.dumps({'ok': report['ok'], 'report': str(output)}), flush=True)
            return 0 if report['ok'] else 1
        if session['state'] == 'recovering' and session.get('error'):
            report['session'] = session
            save()
            raise RuntimeError('Recovery requires inspection; do not restart the experiment')
        time.sleep(2)


if __name__ == '__main__':
    raise SystemExit(main())

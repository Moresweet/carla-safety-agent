"""Native background scheduler regression; GET polling never advances jobs."""
import hashlib
import argparse
import json
import time
from urllib.error import HTTPError
from carla_safety_agent.batch_catalog import BatchCatalog
from carla_safety_agent.experiment_matrix import canonical
from regression_scene_versions import ROOT, request
from regression_rule_move import ACTIVE, wait_terminal
from validate_completed_batch import validate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', choices=('rule-run', 'uniad-tiny', 'vad'), default='rule-run')
    parser.add_argument('--seeds', type=int, nargs='+', default=[31, 32])
    args = parser.parse_args()
    assert request('system/preflight')['ready']
    assert request('batches/scheduler')['scheduler']['state'] != 'running'
    plan = request('scenario/compile', {'description': 'Town04 前车急刹', 'max_duration_s': 1})
    variant = lambda value: {'id': 'baseline', 'configuration': value}
    dimensions = {'scenes': [variant({'scenario': plan['scenario'],
        'scenario_sha256': hashlib.sha256(canonical(plan['scenario'])).hexdigest()})],
        'models': [variant({'action': 'rule-run'} if args.model == 'rule-run' else
                           {'action': 'run', 'algorithm': args.model})], 'weather': [variant({})],
        'textures': [variant({})], 'seeds': args.seeds}
    batch_id = request('batches/create', dimensions)['batch_id']
    catalog = BatchCatalog(ROOT/'data/experiment-queues')
    try:
        started = request('batches/scheduler', {'batch_id': batch_id, 'action': 'start'})
        assert started['scheduler']['batch_id'] == batch_id
        for payload in ({'batch_id': batch_id, 'action': 'start'},
                        {'batch_id': 'wrong-owner', 'action': 'cancel'}):
            try:
                request('batches/scheduler', payload)
            except HTTPError as exc:
                assert exc.code == 400
            else:
                raise AssertionError('Unsafe scheduler control accepted')
        deadline = time.monotonic()+600*len(args.seeds)
        while time.monotonic() < deadline:
            status = request('batches/scheduler')['scheduler']
            assert status['batch_id'] == batch_id
            if status['state'] != 'running':
                break
            time.sleep(.5)
        assert status['state'] == 'completed', status
        result = validate(batch_id)
        assert all(row['attempt_count'] == 1 for row in result['verified'])
        import carla
        client = carla.Client('127.0.0.1', 2000); client.set_timeout(10)
        world = client.get_world()
        assert not world.get_settings().synchronous_mode
        assert not list(world.get_actors().filter('sensor.*'))
        result.update(background_completed=True, duplicate_start_rejected=True,
                      wrong_owner_cancel_rejected=True, native_cleanup_verified=True,
                      model=args.model, seeds=args.seeds)
    finally:
        status = request('batches/scheduler')['scheduler']
        if status['batch_id'] == batch_id and status['state'] == 'running':
            request('batches/scheduler', {'batch_id': batch_id, 'action': 'cancel'})
            deadline = time.monotonic()+40
            while time.monotonic() < deadline:
                if request('batches/scheduler')['scheduler']['state'] != 'running':
                    break
                time.sleep(.5)
            else:
                raise RuntimeError('Scheduler still active; refusing concurrent simulation cleanup')
        session = request('session/status')['session']
        attempts = {a['attempt_id'] for j in catalog.read(batch_id)['jobs'] for a in j['attempts']}
        if session.get('configuration', {}).get('request', {}).get('batch_attempt_id') in attempts and session['state'] in ACTIVE:
            request('scenario/stop' if session['kind'] == 'rule-run' else 'e2e/stop',
                    {'run_id': session['run_id']})
            wait_terminal(session['run_id'])
    output = ROOT/'runs/validation'/('batch-service-'+batch_id+'.json')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()

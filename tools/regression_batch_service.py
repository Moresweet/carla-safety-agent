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


def cancel_and_resume(batch_id, scheduler_id, catalog):
    """Cancel only scheduling while the first native execution remains owned/live."""
    from carla_safety_agent.session import observed_process_identity
    deadline = time.monotonic()+120
    while time.monotonic() < deadline:
        jobs = catalog.read(batch_id)['jobs']
        session = request('session/status')['session']
        if (jobs[0]['state'] == 'running' and session['state'] in ACTIVE
                and session.get('process') and observed_process_identity(session['process']['pid']) == session['process']):
            break
        time.sleep(.2)
    else:
        raise AssertionError('No live first execution observed before cancellation')
    execution = session['run_id']
    assert session['configuration']['request']['batch_attempt_id'] == jobs[0]['attempts'][-1]['attempt_id']
    request('batches/scheduler', {'batch_id': batch_id, 'action': 'cancel', 'scheduler_id': scheduler_id})
    deadline = time.monotonic()+40
    while time.monotonic() < deadline:
        status = request('batches/scheduler')['scheduler']
        assert status['scheduler_id'] == scheduler_id
        if status['state'] != 'running':
            break
        time.sleep(.2)
    assert status['state'] == 'cancelled', status
    current = request('session/status')['session']
    assert current['run_id'] == execution and current['state'] in ACTIVE
    assert observed_process_identity(current['process']['pid']) == current['process']
    assert all(not job['attempts'] for job in catalog.read(batch_id)['jobs'][1:])
    terminal = wait_terminal(execution)
    assert terminal['state'] == 'completed', terminal
    assert all(not job['attempts'] for job in catalog.read(batch_id)['jobs'][1:])
    resumed = request('batches/scheduler', {'batch_id': batch_id, 'action': 'start'})['scheduler']
    assert resumed['scheduler_id'] != scheduler_id
    return {'cancelled_scheduler_id': scheduler_id, 'resumed_scheduler_id': resumed['scheduler_id'],
            'preserved_execution_id': execution, 'current_execution_survived_cancel': True,
            'remaining_jobs_not_started_before_resume': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    choices = ('rule-run', 'uniad-tiny', 'uniad-base', 'vad', 'tcp', 'admlp')
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument('--model', choices=choices)
    selection.add_argument('--models', choices=choices, nargs='+')
    parser.add_argument('--seeds', type=int, nargs='+', default=[31, 32])
    parser.add_argument('--cancel-resume', action='store_true')
    args = parser.parse_args()
    models = args.models or [args.model or 'rule-run']
    if len(set(models)) != len(models):
        parser.error('Duplicate model variants')
    if args.cancel_resume and (models != ['rule-run'] or len(args.seeds) < 2):
        parser.error('Cancellation regression requires rule-run and at least two seeds')
    assert request('system/preflight')['ready']
    assert request('batches/scheduler')['scheduler']['state'] != 'running'
    plan = request('scenario/compile', {'description': 'Town04 前车急刹', 'max_duration_s': 1})
    variant = lambda value: {'id': 'baseline', 'configuration': value}
    dimensions = {'scenes': [variant({'scenario': plan['scenario'],
        'scenario_sha256': hashlib.sha256(canonical(plan['scenario'])).hexdigest()})],
        'models': [{'id': model, 'configuration': {'action': 'rule-run'} if model == 'rule-run' else
                    {'action': 'run', 'algorithm': model}} for model in models], 'weather': [variant({})],
        'textures': [variant({})], 'seeds': args.seeds}
    batch_id = request('batches/create', dimensions)['batch_id']
    catalog = BatchCatalog(ROOT/'data/experiment-queues')
    try:
        started = request('batches/scheduler', {'batch_id': batch_id, 'action': 'start'})
        assert started['scheduler']['batch_id'] == batch_id
        for payload in ({'batch_id': batch_id, 'action': 'start'},
                        {'batch_id': 'wrong-owner', 'action': 'cancel',
                         'scheduler_id': started['scheduler']['scheduler_id']}):
            try:
                request('batches/scheduler', payload)
            except HTTPError as exc:
                assert exc.code == 400
            else:
                raise AssertionError('Unsafe scheduler control accepted')
        cancellation = cancel_and_resume(batch_id, started['scheduler']['scheduler_id'], catalog) if args.cancel_resume else {}
        deadline = time.monotonic()+600*len(args.seeds)*len(models)
        while time.monotonic() < deadline:
            status = request('batches/scheduler')['scheduler']
            assert status['batch_id'] == batch_id
            if status['state'] != 'running':
                break
            time.sleep(.5)
        assert status['state'] == 'completed', status
        result = validate(batch_id)
        result.update(cancellation)
        if cancellation:
            assert result['verified'][0]['execution_id'] == cancellation['preserved_execution_id']
        assert all(row['attempt_count'] == 1 for row in result['verified'])
        from carla_safety_agent.session import SessionJournal
        journal = SessionJournal(ROOT/'data')
        records = [journal.read_execution(row['execution_id']) for row in result['verified']]
        observed = [record['configuration']['request'].get('algorithm', 'rule-run') for record in records]
        assert observed == [model for model in models for _ in args.seeds], observed
        assert all(previous['ended_at'] <= following['started_at']
                   for previous, following in zip(records, records[1:]))
        import carla
        client = carla.Client('127.0.0.1', 2000); client.set_timeout(10)
        world = client.get_world()
        assert not world.get_settings().synchronous_mode
        assert not list(world.get_actors().filter('sensor.*'))
        result.update(background_completed=True, duplicate_start_rejected=True,
                      wrong_owner_cancel_rejected=True, native_cleanup_verified=True,
                      models=models, seeds=args.seeds, sequential_model_identity_verified=True)
    finally:
        status = request('batches/scheduler')['scheduler']
        if status['batch_id'] == batch_id and status['state'] == 'running':
            request('batches/scheduler', {'batch_id': batch_id, 'action': 'cancel',
                                         'scheduler_id': status['scheduler_id']})
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

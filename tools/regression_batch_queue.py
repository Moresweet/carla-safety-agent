"""Opt-in native two-seed queue regression with unified capture validation."""
import hashlib
import argparse
import json
import subprocess
import sys
import time
import uuid
from pathlib import Path
from carla_safety_agent.experiment_matrix import canonical
from carla_safety_agent.experiment_queue import ExperimentQueue
from carla_safety_agent.experiment_dispatch import advance_queue
from carla_safety_agent.session import SessionJournal
from regression_scene_versions import ROOT, request
from regression_rule_move import ACTIVE, wait_terminal


def restore_test_weather(queue_state, session, journal, world):
    attempts = [a for j in queue_state['jobs'] for a in j['attempts']]
    owned = {a['attempt_id'] for a in attempts}
    current = session.get('configuration', {}).get('request', {})
    if current.get('batch_attempt_id') not in owned:
        raise RuntimeError('Session ownership changed; refusing weather restoration')
    if session['state'] in ACTIVE or world.get_settings().synchronous_mode:
        raise RuntimeError('World is not idle; refusing weather restoration')
    executions = [a['execution_id'] for a in attempts if a.get('execution_id')]
    if not executions:
        return False
    original = journal.read_execution(executions[0])['configuration']['starting_scene']
    if world.get_map().name != original['map']:
        raise RuntimeError('Map changed; refusing weather restoration')
    weather = world.get_weather()
    for key, value in original['weather'].items():
        if not hasattr(weather, key):
            raise RuntimeError('Unsupported saved weather property')
        setattr(weather, key, value)
    world.set_weather(weather)
    observed = world.get_weather()
    assert all(abs(getattr(observed, key)-value) < 1e-4 for key, value in original['weather'].items())
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--weather-ab', action='store_true')
    parser.add_argument('--http', action='store_true', help='Create and control the queue through the live bridge')
    args = parser.parse_args()
    assert request('system/preflight')['ready']
    plan = request('scenario/compile', {'description': 'Town04 前车急刹', 'max_duration_s': 1})
    variant = lambda config: {'id': 'baseline', 'configuration': config}
    dimensions = {'scenes': [variant({'scenario': plan['scenario'],
        'scenario_sha256': hashlib.sha256(canonical(plan['scenario'])).hexdigest()})],
        'models': [variant({'action': 'rule-run'})], 'weather': [variant({})],
        'textures': [variant({})], 'seeds': [31, 32]}
    if args.weather_ab:
        dimensions['seeds'] = [31]
        dimensions['weather'] = [{'id': 'clear', 'configuration': {'precipitation': 0}},
                                 {'id': 'rain', 'configuration': {'precipitation': 75}}]
    batch_id = None
    if args.http:
        created = request('batches/create', dimensions)
        assert created['dispatched'] is False
        batch_id = created['batch_id']
        from carla_safety_agent.scene_store import identifier
        identifier(batch_id)
        root = ROOT/'data/experiment-queues'/batch_id
    else:
        root = ROOT/'runs/validation'/('batch-queue-'+uuid.uuid4().hex)
    q = ExperimentQueue(root)
    if not args.http:
        q.create(dimensions)
    journal = SessionJournal(ROOT/'data')
    def step():
        if args.http:
            return request('batches/control', {'batch_id': batch_id, 'action': 'advance'})
        return advance_queue(ExperimentQueue(root), journal, ROOT/'.runtime/generated-scenarios', request)
    def pause(value):
        if args.http:
            return request('batches/control', {'batch_id': batch_id, 'action': 'pause' if value else 'resume'})
        return q.set_paused(value)
    paused_once = resumed_once = False
    try:
        deadline = time.monotonic()+180
        while time.monotonic() < deadline:
            # Reconstruct clients each step to test persisted state, not memory.
            result = step()
            if result['action'] == 'started' and not paused_once:
                pause(True)
                paused_once = True
            if result['action'] == 'paused' and not resumed_once:
                snapshot = q.read()
                assert snapshot['jobs'][0]['state'] == 'completed'
                assert snapshot['jobs'][1]['state'] == 'pending'
                assert snapshot['jobs'][1]['attempts'] == []
                session = request('session/status')['session']
                for _ in range(3):
                    assert step()['action'] == 'paused'
                    assert request('session/status')['session']['run_id'] == session['run_id']
                pause(False)
                resumed_once = True
            if result['action'] == 'no_pending_jobs':
                break
            if result['action'] in ('started', 'preparation_failed'):
                print(json.dumps(result), flush=True)
            time.sleep(.5)
        jobs = q.read()['jobs']
        assert paused_once and resumed_once
        assert all(j['state'] == 'completed' and len(j['attempts']) == 1 for j in jobs), jobs
        executions = [j['attempts'][0]['execution_id'] for j in jobs]
        assert len(set(executions)) == 2
        datasets = []
        for index, (seed, execution) in enumerate(zip([31, 31] if args.weather_ab else [31, 32], executions)):
            record = journal.read_execution(execution)
            outcome = json.loads(Path(record['configuration']['results']).read_text())
            assert outcome['scenario']['seed'] == seed
            if args.weather_ab:
                assert outcome['scenario']['environment']['precipitation'] == [0, 75][index]
            captures = [p.parent for p in (ROOT/'.runtime/generated-scenarios').glob('capture-*/manifest.json')
                        if json.loads(p.read_text()).get('execution_id') == execution]
            assert len(captures) == 1
            subprocess.run([sys.executable, str(ROOT/'tools/validate_capture_dataset.py'), str(captures[0])], check=True)
            datasets.append(str(captures[0]))
        import carla
        client = carla.Client('127.0.0.1', 2000); client.set_timeout(10)
        world = client.get_world()
        assert not world.get_settings().synchronous_mode
        assert not list(world.get_actors().filter('sensor.*'))
        report = {'executions': executions, 'datasets': datasets, 'queue': str(root), 'passed': True,
                  'http': args.http, 'batch_id': batch_id,
                  'paused_after_first_start': paused_once, 'resumed_after_first_completed': resumed_once}
        if args.http:
            summary = request('batches/report?batch_id='+batch_id)['report']
            assert summary['all_executions_completed']
            assert all(row.get('metrics') and not row.get('metrics_error') for row in summary['rows'])
            report['http_metrics_verified'] = True
        if args.weather_ab:
            from carla_safety_agent.experiment_report import summarize_queue, compare_variants
            summary = summarize_queue(q.read(), ROOT/'runs/rule')
            comparison = compare_variants(summary, 'weather', 'clear', 'rain')
            assert comparison['comparable_count'] == 1, comparison
            if args.http:
                observed = request('batches/compare?batch_id='+batch_id+
                                   '&axis=weather&baseline=clear&candidate=rain')['comparison']
                assert observed == comparison, (observed, comparison)
                report['http_comparison_verified'] = True
            report['comparison'] = comparison
            (root/'summary.json').write_text(json.dumps(summary, indent=2))
    finally:
        session = request('session/status')['session']
        request_data = session.get('configuration', {}).get('request', {})
        attempts = {a['attempt_id'] for j in q.read()['jobs'] for a in j['attempts']}
        if request_data.get('batch_attempt_id') in attempts and session['state'] in ACTIVE:
            request('scenario/stop', {'run_id': session['run_id']})
            wait_terminal(session['run_id'])
        if args.weather_ab and request_data.get('batch_attempt_id') in attempts:
            executions = [a['execution_id'] for j in q.read()['jobs'] for a in j['attempts'] if a.get('execution_id')]
            restored = request('session/restore-weather', {'run_id': session['run_id'], 'source_run_id': executions[0]})
            assert restored['weather_restored'] is True
            print(json.dumps({'test_weather_restored': True}), flush=True)
    (root/'report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report), flush=True)


if __name__ == '__main__': main()

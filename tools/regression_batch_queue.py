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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--weather-ab', action='store_true')
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
    root = ROOT/'runs/validation'/('batch-queue-'+uuid.uuid4().hex)
    q = ExperimentQueue(root); q.create(dimensions)
    journal = SessionJournal(ROOT/'data')
    paused_once = resumed_once = False
    try:
        deadline = time.monotonic()+180
        while time.monotonic() < deadline:
            # Reconstruct clients each step to test persisted state, not memory.
            result = advance_queue(ExperimentQueue(root), journal,
                                   ROOT/'.runtime/generated-scenarios', request)
            if result['action'] == 'started' and not paused_once:
                q.set_paused(True)
                paused_once = True
            if result['action'] == 'paused' and not resumed_once:
                snapshot = q.read()
                assert snapshot['jobs'][0]['state'] == 'completed'
                assert snapshot['jobs'][1]['state'] == 'pending'
                assert snapshot['jobs'][1]['attempts'] == []
                session = request('session/status')['session']
                for _ in range(3):
                    assert advance_queue(ExperimentQueue(root), journal,
                        ROOT/'.runtime/generated-scenarios', request)['action'] == 'paused'
                    assert request('session/status')['session']['run_id'] == session['run_id']
                q.set_paused(False)
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
                  'paused_after_first_start': paused_once, 'resumed_after_first_completed': resumed_once}
        if args.weather_ab:
            from carla_safety_agent.experiment_report import summarize_queue, compare_variants
            summary = summarize_queue(q.read(), ROOT/'runs/rule')
            comparison = compare_variants(summary, 'weather', 'clear', 'rain')
            assert comparison['comparable_count'] == 1, comparison
            report['comparison'] = comparison
            (root/'summary.json').write_text(json.dumps(summary, indent=2))
        (root/'report.json').write_text(json.dumps(report, indent=2))
        print(json.dumps(report), flush=True)
    finally:
        session = request('session/status')['session']
        request_data = session.get('configuration', {}).get('request', {})
        attempts = {a['attempt_id'] for j in q.read()['jobs'] for a in j['attempts']}
        if request_data.get('batch_attempt_id') in attempts and session['state'] in ACTIVE:
            request('scenario/stop', {'run_id': session['run_id']})
            wait_terminal(session['run_id'])


if __name__ == '__main__': main()

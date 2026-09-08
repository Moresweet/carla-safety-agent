"""Native opt-in: interrupt only the scheduler, then resume the same batch."""
import json
import hashlib
import select
import signal
import subprocess
import sys
from carla_safety_agent.batch_catalog import BatchCatalog
from carla_safety_agent.experiment_matrix import canonical
from regression_scene_versions import ROOT, request
from regression_rule_move import ACTIVE, wait_terminal
from validate_completed_batch import validate


def main():
    assert request('system/preflight')['ready']
    catalog = BatchCatalog(ROOT/'data/experiment-queues')
    plan = request('scenario/compile', {'description': 'Town04 前车急刹', 'max_duration_s': 1})
    variant = lambda value: {'id': 'baseline', 'configuration': value}
    dimensions = {'scenes': [variant({'scenario': plan['scenario'],
        'scenario_sha256': hashlib.sha256(canonical(plan['scenario'])).hexdigest()})],
        'models': [variant({'action': 'rule-run'})], 'weather': [variant({})],
        'textures': [variant({})], 'seeds': [31, 32]}
    batch_id = request('batches/create', dimensions)['batch_id']
    command = [sys.executable, str(ROOT/'tools/run_batch_queue.py'), batch_id]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert select.select([process.stdout], [], [], 60)[0], 'No scheduler startup response'
        first = json.loads(process.stdout.readline())
        assert first['action'] == 'started', first
        process.send_signal(signal.SIGINT)
        output, error = process.communicate(timeout=40)
        assert process.returncode == 2, (output, error)
        cancelled = json.loads(output.strip().splitlines()[-1])
        assert cancelled['state'] == 'cancelled'
        assert cancelled['current_simulation_stopped'] is False
        session = wait_terminal(first['execution_id'])
        assert session['state'] == 'completed'
        before = catalog.read(batch_id)
        assert len(before['jobs'][0]['attempts']) == 1
        assert before['jobs'][1]['state'] == 'pending' and before['jobs'][1]['attempts'] == []
        resumed = subprocess.run(command, capture_output=True, text=True, timeout=180)
        assert resumed.returncode == 0, (resumed.stdout, resumed.stderr)
        result = validate(batch_id)
        assert all(item['attempt_count'] == 1 for item in result['verified'])
        assert result['verified'][0]['execution_id'] == first['execution_id']
        import carla
        client = carla.Client('127.0.0.1', 2000); client.set_timeout(10)
        world = client.get_world()
        assert not world.get_settings().synchronous_mode
        assert not list(world.get_actors().filter('sensor.*'))
        result.update(scheduler_cancelled=True, resumed_without_duplicate=True, native_cleanup_verified=True)
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
            process.communicate(timeout=40)
        session = request('session/status')['session']
        attempts = {a['attempt_id'] for j in catalog.read(batch_id)['jobs'] for a in j['attempts']}
        if session.get('configuration', {}).get('request', {}).get('batch_attempt_id') in attempts and session['state'] in ACTIVE:
            request('scenario/stop', {'run_id': session['run_id']})
            wait_terminal(session['run_id'])
    output = ROOT/'runs/validation'/('batch-resume-'+batch_id+'.json')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()

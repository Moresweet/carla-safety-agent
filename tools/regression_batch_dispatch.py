"""Native short rule execution with identical and conflicting HTTP retries."""
import json
import uuid
import urllib.error
from regression_scene_versions import ROOT, request
from regression_rule_move import wait_terminal, ACTIVE


def main():
    assert request('system/preflight')['ready']
    plan = request('scenario/compile', {'description': 'Town04 前车急刹', 'max_duration_s': 1})
    options = {'action': 'rule-run', 'route': plan['scenario_path'],
               'scenario_sha256': plan['scenario_sha256'], 'unified_capture': False,
               'batch_attempt_id': uuid.uuid4().hex, 'batch_job_id': uuid.uuid4().hex}
    execution = None
    try:
        first = request('e2e/start', options)
        execution = first['execution_id']
        assert first['replayed'] is False
        repeated = request('e2e/start', options)
        assert repeated['replayed'] is True and repeated['execution_id'] == execution
        try:
            request('e2e/start', {**options, 'unified_capture': True})
        except urllib.error.HTTPError as exc:
            assert 'changed after dispatch' in exc.read().decode()
        else:
            raise AssertionError('Conflicting request accepted')
        session = wait_terminal(execution)
        assert session['state'] == 'completed', session
        terminal_retry = request('e2e/start', options)
        assert terminal_retry['replayed'] is True and terminal_retry['execution_id'] == execution
        from carla_safety_agent.session import SessionJournal
        record = SessionJournal(ROOT/'data').find_batch_attempt(options['batch_attempt_id'], options['batch_job_id'])
        assert record['run_id'] == execution and record['state'] == 'completed'
        import carla
        client = carla.Client('127.0.0.1', 2000); client.set_timeout(10)
        world = client.get_world()
        assert not world.get_settings().synchronous_mode
        assert not list(world.get_actors().filter('sensor.*'))
        report = {'execution_id': execution, 'same_request_reused': True,
                  'terminal_retry_reused': True, 'changed_request_rejected': True,
                  'world_async': True, 'sensors_remaining': 0}
        output = ROOT/'runs/validation'/f'batch-dispatch-{execution}.json'
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2))
        print(json.dumps(report), flush=True)
    finally:
        if execution:
            session = request('session/status')['session']
            if session['run_id'] == execution and session['state'] in ACTIVE:
                request('scenario/stop', {'run_id': execution})
                wait_terminal(execution)


if __name__ == '__main__': main()

import pytest
from carla_safety_agent.batch_runner import run_batch


def test_serial_runner_waits_for_reconciliation():
    steps = iter([{'action': 'started'}, {'action': 'reconcile', 'reconciled': False},
                  {'action': 'reconcile', 'reconciled': True, 'state': 'completed'},
                  {'action': 'started'}, {'action': 'reconcile', 'reconciled': True, 'state': 'completed'},
                  {'action': 'no_pending_jobs', 'states': ['completed', 'completed']}])
    observed, waits = [], []
    result = run_batch(lambda: next(steps), lambda: waits.append(True), observe=observed.append)
    assert result['state'] == 'completed' and len(waits) == 5 and len(observed) == 6


@pytest.mark.parametrize('step', [
    {'action': 'recover_binding', 'bound': False},
    {'action': 'reconcile', 'reconciled': True, 'state': 'failed'},
    {'action': 'preflight_blocked'}, {'action': 'dispatcher_busy'},
    {'action': 'preparation_failed'}, {'action': 'unknown'},
    {'action': 'no_pending_jobs', 'states': ['failed']},
])
def test_uncertainty_or_failure_stops_without_wait_or_retry(step):
    assert run_batch(lambda: step, lambda: pytest.fail('must stop'))['state'] == 'needs_attention'


def test_pause_cancel_and_transport_failure():
    assert run_batch(lambda: {'action': 'paused'}, lambda: None)['state'] == 'paused'
    assert run_batch(lambda: pytest.fail('cancelled'), lambda: None,
                     cancelled=lambda: True)['current_simulation_stopped'] is False
    def fail():
        raise OSError('response lost')
    with pytest.raises(OSError):
        run_batch(fail, lambda: pytest.fail('must not retry'))

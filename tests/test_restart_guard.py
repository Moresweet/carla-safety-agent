import pytest
from carla_safety_agent.restart_guard import verify_idle


@pytest.mark.parametrize('scheduler', [{'state': 'running'}, {}, None])
def test_restart_refuses_scheduler_even_between_simulations(scheduler):
    with pytest.raises(ValueError, match='scheduler'):
        verify_idle({'state': 'completed'}, scheduler)


def test_restart_requires_terminal_session_and_dead_owned_process():
    scheduler = {'state': 'completed'}
    with pytest.raises(ValueError):
        verify_idle({'state': 'running'}, scheduler)
    identity = {'pid': 42, 'start_ticks': '100'}
    session = {'state': 'completed', 'process': identity}
    with pytest.raises(ValueError, match='still alive'):
        verify_idle(session, scheduler, lambda pid: identity)
    verify_idle(session, scheduler, lambda pid: None)
    verify_idle(session, scheduler, lambda pid: {'pid': 42, 'start_ticks': '200'})
    with pytest.raises(PermissionError):
        def denied(pid):
            raise PermissionError('Cannot inspect process')
        verify_idle(session, scheduler, denied)

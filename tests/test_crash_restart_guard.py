import pytest
from carla_safety_agent.restart_guard import verify_crash_restart


def test_dead_recovery_can_restart_without_changing_journal():
    session={'state':'recovering','process':{'pid':42,'start_ticks':'a'}}
    verify_crash_restart(session,{'state':'idle'},False,False,observe=lambda _:None)
    assert session['state']=='recovering'


@pytest.mark.parametrize('native,port',[(True,False),(False,True),(True,True)])
def test_live_native_or_port_cannot_be_treated_as_crashed(native,port):
    with pytest.raises(ValueError):
        verify_crash_restart({'state':'recovering'},{'state':'idle'},native,port)


def test_active_worker_and_batch_still_block_crash_restart():
    identity={'pid':42,'start_ticks':'a'}
    with pytest.raises(ValueError,match='still alive'):
        verify_crash_restart({'state':'recovering','process':identity},{'state':'idle'},False,False,
                             observe=lambda _:identity)
    with pytest.raises(ValueError,match='scheduler'):
        verify_crash_restart({'state':'recovering'},{'state':'running'},False,False)

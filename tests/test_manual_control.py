import pytest
from carla_safety_agent.manual_control import current_control,validate_control,SAFE_CONTROL


def test_manual_command_expires_and_cannot_cross_execution():
    command={'execution_id':'run','issued_monotonic':10,'control':{'throttle':.4,'steer':-.3}}
    assert current_control(command,'run',10.2)['throttle']==.4
    for run,now in (('other',10.2),('run',10.6),('run',9)):
        assert current_control(command,run,now)==SAFE_CONTROL
    assert current_control(None,'run',10)==SAFE_CONTROL


@pytest.mark.parametrize('payload',[{'throttle':2},{'steer':float('nan')},{'brake':True},{'reverse':'false'}])
def test_manual_values_must_be_valid(payload):
    with pytest.raises(ValueError): validate_control(payload)

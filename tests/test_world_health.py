from types import SimpleNamespace as NS
import pytest

from carla_safety_agent.world_health import observe_idle


def fixture():
    tick={'time':0.,'frame':0,'synchronous':False,'sensors':[]}
    def snapshot():
        tick['frame']+=1
        return NS(frame=tick['frame'])
    world=NS(id=1,get_map=lambda:NS(name='Carla/Maps/Town04'),
             get_settings=lambda:NS(synchronous_mode=tick['synchronous']),
             get_actors=lambda:NS(filter=lambda _:tick['sensors']),get_snapshot=snapshot)
    client=NS(get_world=lambda:world)
    return tick,world,client


def test_post_exit_health_observes_progress_without_ticking():
    state,world,client=fixture()
    result=observe_idle(client,'Town04',1,clock=lambda:state['time'],
                        pause=lambda dt:state.update(time=state['time']+dt))
    assert result['checks']==5 and result['frames_first_last']==[1,5]


@pytest.mark.parametrize('failure',['stalled','map_changed','sensor','sync','server_dead'])
def test_post_exit_failure_is_not_reported_healthy(failure):
    state,world,client=fixture()
    def pause(dt):
        state['time']+=dt
        if failure=='stalled':world.get_snapshot=lambda:NS(frame=1)
        elif failure=='map_changed':world.id=2
        elif failure=='sensor':state['sensors']=[NS(id=5)]
        elif failure=='sync':state['synchronous']=True
        elif failure=='server_dead':
            def dead():raise RuntimeError('server unavailable')
            client.get_world=dead
    with pytest.raises((ValueError,RuntimeError)):
        observe_idle(client,'Town04',1,clock=lambda:state['time'],pause=pause)

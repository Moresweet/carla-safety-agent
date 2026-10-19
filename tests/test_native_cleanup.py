import ast
from pathlib import Path
from types import SimpleNamespace as NS
import pytest
from carla_safety_agent.runtime_cleanup import Cleanup, cleanup_native_runtime, cleanup_rule_runtime


def rig_class():
    source=Path(__file__).resolve().parents[1]/'src/carla_safety_agent/native_executor.py'
    node=next(n for n in ast.parse(source.read_text()).body if isinstance(n,ast.ClassDef) and n.name=='NativeSensorRig')
    env={'Any':object,'Cleanup':Cleanup}
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(source),'exec'),env)
    return env['NativeSensorRig']


@pytest.mark.parametrize('tags', [('SPEED',), ('speed',), ('speed', 'aux_speed')])
def test_speed_callback_uses_declared_sensor_ids(tags):
    registered, received = [], []
    interface = NS(register_sensor=lambda tag, *args: registered.append(tag),
                   update_sensor=lambda tag, data, frame: received.append((tag, data, frame)))
    ego = NS(get_velocity=lambda: NS(x=3., y=4., z=0.),
             get_transform=lambda: NS(get_forward_vector=lambda: NS(x=.6, y=.8, z=0.)))
    rig = rig_class()(None, None, ego, interface)
    rig.setup([{'id': tag, 'type': 'sensor.speedometer'} for tag in tags])
    rig.add_speed(123)
    assert registered == list(tags)
    assert received == [(tag, {'speed': 5.}, 123) for tag in tags]


def test_lidar_callback_decodes_owned_xyzi_array():
    import numpy as np
    callbacks, received = [], []
    sensor = NS(id=42, listen=callbacks.append)
    world = NS(get_blueprint_library=lambda: NS(find=lambda _: NS(has_attribute=lambda _: False)),
               spawn_actor=lambda *args, **kwargs: sensor)
    carla = NS(Transform=lambda *args: None, Location=lambda **kwargs: None,
               Rotation=lambda **kwargs: None)
    interface = NS(register_sensor=lambda *args: None,
                   update_sensor=lambda tag, value, frame: received.append((tag, value, frame)))
    rig = rig_class()(carla, world, None, interface)
    rig.setup([{'id': 'lidar', 'type': 'sensor.lidar.ray_cast'}])
    raw = bytearray(np.arange(8, dtype=np.float32).tobytes())
    callbacks[0](NS(raw_data=raw, frame=20))
    raw[:] = bytes(len(raw))
    assert received[0][0] == 'lidar' and received[0][2] == 20
    np.testing.assert_array_equal(received[0][1], np.arange(8, dtype=np.float32).reshape(2, 4))


@pytest.mark.parametrize('supported', [True, False])
def test_explicit_blueprint_attributes_are_required_before_spawn(supported):
    calls = []
    blueprint = NS(has_attribute=lambda name: supported,
                   set_attribute=lambda name, value: calls.append((name, value)))
    sensor = NS(id=42, listen=lambda cb: None)
    def spawn(*args, **kwargs):
        calls.append('spawn')
        return sensor
    world = NS(get_blueprint_library=lambda: NS(find=lambda _: blueprint), spawn_actor=spawn)
    carla = NS(Transform=lambda *a: None, Location=lambda **kw: None, Rotation=lambda **kw: None)
    rig = rig_class()(carla, world, None, NS(register_sensor=lambda *a: None))
    specs = [{'id': 'lidar', 'type': 'sensor.lidar.ray_cast',
              'blueprint_attributes': {'channels': '64'}}]
    if supported:
        rig.setup(specs)
        assert calls == [('channels', '64'), 'spawn']
    else:
        with pytest.raises(ValueError, match='required blueprint attribute unavailable: channels'):
            rig.setup(specs)
        assert calls == []


@pytest.mark.parametrize('failure',['register','listen'])
def test_partially_initialized_sensor_remains_owned_for_cleanup(failure):
    calls=[]
    def fail(): raise RuntimeError('setup failed')
    sensor=NS(id=1,is_alive=True,stop=lambda:calls.append('stop'),destroy=lambda:calls.append('destroy') or True,
        listen=lambda _:fail() if failure=='listen' else None)
    world=NS(get_blueprint_library=lambda:NS(find=lambda _:NS(has_attribute=lambda _:False)),
        spawn_actor=lambda *a,**kw:sensor)
    carla=NS(Transform=lambda *a:None,Location=lambda **kw:None,Rotation=lambda **kw:None)
    interface=NS(register_sensor=lambda *a:fail() if failure=='register' else None)
    rig=rig_class()(carla,world,None,interface)
    with pytest.raises(RuntimeError): rig.setup([{'id':'CAM','type':'sensor.camera.rgb'}])
    assert rig.sensors==[sensor]
    rig.destroy()
    assert calls==['stop','destroy'] and rig.sensors==[]


def test_sensor_stop_failure_does_not_prevent_destroying_other_sensors():
    calls=[]
    def stop(): calls.append('stop1'); raise RuntimeError('stop failure')
    a=NS(id=1,is_alive=True,stop=stop,destroy=lambda:calls.append('destroy1') or False)
    b=NS(id=2,is_alive=True,stop=lambda:calls.append('stop2'),destroy=lambda:calls.append('destroy2') or True)
    rig=rig_class()(None,None,None,None);rig.sensors=[a,b]
    with pytest.raises(RuntimeError,match='destroy returned false'): rig.destroy()
    assert calls==['stop1','stop2','destroy1','destroy2'] and rig.sensors==[a]


def test_rig_uses_server_ack_even_if_new_sensor_not_in_snapshot():
    calls=[]
    sensor=NS(id=42,is_alive=False,stop=lambda:calls.append('stop'))
    carla=NS(command=NS(DestroyActor=lambda actor_id:actor_id))
    client=NS(apply_batch_sync=lambda ids,tick:calls.append((ids,tick)) or [NS(error='')])
    rig=rig_class()(carla,None,None,None,client=client)
    rig.sensors=[sensor]
    rig.destroy()
    assert calls==['stop',([42],False)] and rig.sensors==[]


@pytest.mark.parametrize('failure',['capture_raise','capture_report','rig','model','stop','actors','settings'])
def test_every_runtime_cleanup_step_attempted_despite_failure(failure):
    calls=[]
    def operation(name):
        calls.append(name)
        if failure==name or (name=='capture' and failure=='capture_raise'):
            raise RuntimeError(name+' failed')
        if name=='capture': return ['disk full'] if failure=='capture_report' else []
    carla=NS(command=NS(DestroyActor=lambda i:i))
    client=NS(apply_batch=lambda ids:operation('actors'))
    world=NS(apply_settings=lambda _:operation('settings'))
    actors=[NS(id=1,type_id='sensor.other.collision',stop=lambda:operation('stop')),NS(id=2,type_id='vehicle.test')]
    with pytest.raises(RuntimeError,match='cleanup incomplete'):
        cleanup_native_runtime(carla,client,world,'original',actors,
            NS(close=lambda:operation('capture')),NS(destroy=lambda:operation('rig')),NS(destroy=lambda:operation('model')))
    assert calls==['capture','rig','model','stop','actors','settings']


def test_original_failure_remains_in_exception_chain():
    with pytest.raises(RuntimeError,match='cleanup incomplete') as observed:
        try:
            raise ValueError('primary model failure')
        finally:
            cleanup=Cleanup();cleanup.errors=['cleanup failure'];cleanup.finish()
    assert isinstance(observed.value.__context__,ValueError)


def test_recorder_failure_still_destroys_actors_and_restores_world():
    calls=[]
    def fail(*args): calls.append('finalize'); raise OSError('disk full')
    actors=[NS(id=1,is_alive=True,type_id='sensor.camera.rgb',stop=lambda:calls.append('stop')),
            NS(id=2,is_alive=True,type_id='vehicle.test',set_autopilot=lambda _:calls.append('autopilot'))]
    world=NS(get_settings=lambda:NS(synchronous_mode=True),tick=lambda:calls.append('drain'),
        apply_settings=lambda _:calls.append('restore'))
    client=NS(apply_batch=lambda ids:calls.append(ids))
    carla=NS(command=NS(DestroyActor=lambda i:i))
    with pytest.raises(RuntimeError,match='disk full'):
        cleanup_rule_runtime(carla,client,world,'original',actors,None,NS(finalize=fail),None,None,False)
    assert calls==['stop','autopilot','finalize','drain',[1,2],'restore']


@pytest.mark.parametrize('failure',['none','destroy','manager','incomplete'])
def test_rule_owned_manager_cleanup_uses_exact_port_and_acknowledgements(failure):
    calls=[]
    actors=[NS(id=7,is_alive=False,type_id='vehicle.test',
               set_autopilot=lambda enabled,port:calls.append(('autopilot',enabled,port)))]
    def destroy(ids,tick):
        calls.append(('destroy',ids,tick))
        return [] if failure=='incomplete' else [NS(error='failed' if failure=='destroy' else '')]
    def manager_sync(value):
        calls.append(('manager',value))
        if failure=='manager': raise RuntimeError('manager failed')
    world=NS(get_settings=lambda:NS(synchronous_mode=True),tick=lambda:calls.append('drain'),
             apply_settings=lambda _:calls.append('restore'))
    def run():
        cleanup_rule_runtime(NS(command=NS(DestroyActor=lambda i:i)),NS(apply_batch_sync=destroy),
            world,'original',actors,None,None,None,None,False,
            manager=NS(set_synchronous_mode=manager_sync),manager_port=8051)
    if failure=='none': run()
    else:
        with pytest.raises(RuntimeError,match='cleanup incomplete'): run()
    assert calls==[('autopilot',False,8051),'drain',('destroy',[7],False),('manager',False),'restore']


def test_rule_setup_journals_before_world_mutation_and_uses_dedicated_port():
    import inspect
    import textwrap
    from carla_safety_agent.carla_adapter import CarlaAdapter
    tree=ast.parse(textwrap.dedent(inspect.getsource(CarlaAdapter.run)))
    calls=[node for node in ast.walk(tree) if isinstance(node,ast.Call)]
    def lines(name):
        return [node.lineno for node in calls if
                (isinstance(node.func,ast.Name) and node.func.id==name) or
                (isinstance(node.func,ast.Attribute) and node.func.attr==name)]
    assert max(lines('journal_from_environment')) < min(lines('apply_settings'))
    assert max(lines('register_manager')) < min(lines('set_synchronous_mode'))
    for node in calls:
        if isinstance(node.func,ast.Attribute) and node.func.attr=='set_autopilot':
            assert len(node.args)==2 and ast.literal_eval(node.args[1])==8051


@pytest.mark.parametrize('interaction',[False,True])
def test_spawned_actor_is_owned_before_velocity_setup(interaction):
    from carla_safety_agent.carla_adapter import CarlaAdapter
    def fail(*args): raise RuntimeError('velocity setup failed')
    actor=NS(id=1,set_target_velocity=fail)
    blueprint=NS(id='vehicle.test',has_attribute=lambda _:False)
    transform=NS(get_forward_vector=lambda:1,location=NS(z=0.))
    waypoint=NS(next=lambda _:[NS(transform=transform)])
    world=NS(get_blueprint_library=lambda:[blueprint],try_spawn_actor=lambda *a:actor,
        get_map=lambda:NS(get_waypoint=lambda *a,**kw:waypoint))
    spec=NS(blueprint='vehicle.test',spawn_index=0,speed_mps=5,role='ego')
    owned=[]
    with pytest.raises(RuntimeError,match='velocity setup'):
        if interaction:
            CarlaAdapter._spawn_interaction_actor(None,world,NS(get_location=lambda:None),spec,'rear_end',0,owned)
        else:
            CarlaAdapter._spawn(world,spec,[transform],owned)
    assert owned==[actor]
    assert transform.location.z == (.5 if interaction else 0.)


@pytest.mark.parametrize('failure',[KeyboardInterrupt,RuntimeError,None])
def test_model_main_normalizes_only_user_interruption(failure):
    source=Path(__file__).resolve().parents[1]/'src/carla_safety_agent/native_executor.py'
    node=next(n for n in ast.parse(source.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='main')
    args=NS(port=2000,scenario=Path('scenario'),agent=Path('agent'),agent_config='config',output=Path('result'))
    parser=NS(add_argument=lambda *a,**kw:None,parse_args=lambda:args)
    def run(*args):
        if failure: raise failure('test interruption or failure')
    env={'Path':Path,'argparse':NS(ArgumentParser=lambda:parser),'NativeScenarioExecutor':lambda **kw:NS(run=run)}
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(source),'exec'),env)
    if failure==RuntimeError:
        with pytest.raises(RuntimeError):env['main']()
    else:
        assert env['main']()==(130 if failure else 0)

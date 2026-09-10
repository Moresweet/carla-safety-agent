from types import SimpleNamespace as NS
import pytest
from test_studio_bridge import functions


def setup(failure=None):
    calls=[];records={};names=[['old'],['old','BP_AudiA2_C_1']]
    def step(name):
        calls.append(name)
        if failure==name:raise RuntimeError(name+' failed')
    actor=NS(id=7,type_id='vehicle.audi.a2',
        set_autopilot=lambda *_:pytest.fail('Fresh editor spawn must not touch a Traffic Manager'),
        set_simulate_physics=lambda *_:step('physics'),set_target_velocity=lambda *_:step('velocity'),
        set_target_angular_velocity=lambda *_:step('angular'),destroy=lambda:step('destroy') or True)
    blueprint=NS(has_attribute=lambda _:False)
    world=NS(id=10,get_blueprint_library=lambda:NS(find=lambda _:blueprint),
        get_names_of_all_objects=lambda:names.pop(0),spawn_actor=lambda *_:actor,
        wait_for_tick=lambda _:NS(find=lambda _:None))
    def mark(*_):step('mark');records['7']={'stable_id':'stable','type_id':actor.type_id}
    def bind(*args,**metadata):step('bind');records['7'].update(metadata)
    env=functions('_spawn_editor_object',connect_world=lambda:world,
        _provenance=NS(records=lambda _:records,mark=mark,bind=bind),BLENDER=NS(registry=lambda:{}),
        carla=NS(Location=lambda **kw:NS(**kw),Rotation=lambda **kw:NS(**kw),Transform=lambda *args:args,Vector3D=NS,
                 command=NS(DestroyActor=lambda value:value)),
        _carla_client=NS(apply_batch_sync=lambda commands,tick:step('destroy') or [NS(error='',actor_id=7)]),
        _editor_actors=set(),_actor_object_names={},_generated_actor_assets={},
        actor_record=lambda a:step('record') or {'id':a.id})
    return env,calls,records


def test_editor_spawn_persists_exact_name_without_starting_traffic_manager():
    env,calls,records=setup()
    assert env['_spawn_editor_object']('vehicle.audi.a2',{})['object']['id']==7
    assert records['7']['runtime_object_name']=='BP_AudiA2_C_1'
    assert env['_editor_actors']=={7} and 'destroy' not in calls


@pytest.mark.parametrize('failure',['mark','physics','velocity','angular','bind','record'])
def test_post_spawn_failure_deletes_only_owned_actor(failure):
    env,calls,_=setup(failure)
    with pytest.raises(RuntimeError,match=failure+' failed'):env['_spawn_editor_object']('vehicle.audi.a2',{})
    assert calls[-1]=='destroy'
    assert not env['_editor_actors'] and not env['_actor_object_names'] and not env['_generated_actor_assets']


def test_runtime_name_survives_bridge_restart_but_not_type_mismatch():
    actor=NS(id=7,type_id='vehicle.audi.a2')
    record={'type_id':actor.type_id,'runtime_object_name':'BP_AudiA2_C_1'}
    env=functions('runtime_name_for_actor',_actor_object_names={},_provenance=NS(records=lambda _:{'7':record}))
    world=NS(id=2**64-1,get_names_of_all_objects=lambda:['BP_AudiA2_C_1'])
    assert env['runtime_name_for_actor'](world,actor)=='BP_AudiA2_C_1'
    record['type_id']='vehicle.other'
    with pytest.raises(RuntimeError):env['runtime_name_for_actor'](world,actor)


def test_failed_destroy_retains_ownership_and_reports_exact_actor():
    env,_,_=setup('bind')
    env['_carla_client'].apply_batch_sync=lambda *_:[NS(error='refused')]
    with pytest.raises(RuntimeError,match='cleanup unconfirmed for actor 7'):
        env['_spawn_editor_object']('vehicle.audi.a2',{})
    assert env['_editor_actors']=={7}

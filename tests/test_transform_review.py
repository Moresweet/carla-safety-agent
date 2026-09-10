import ast
from pathlib import Path
from types import SimpleNamespace as NS
from typing import Any
import pytest
from carla_safety_agent.transform_review import validate_review,verify_review
from test_studio_bridge import functions


def review():
    return {'episode':'18446744073709551615','actor_id':7,'type_id':'static.prop.test',
            'location':{'x':1.,'y':2.,'z':3.},'yaw':179.99}


def fixture():
    current=NS(location=NS(x=1,y=2,z=3),rotation=NS(yaw=179.99))
    actor=NS(id=7,type_id='static.prop.test',get_transform=lambda:current,
             set_transform=lambda _:pytest.fail('Rejected edit reached native setter'))
    return actor,current


@pytest.mark.parametrize('changes',[{'episode':18446744073709551615},{'episode':str(2**64)},
    {'episode':'-1'},{'episode':'١'},{'actor_id':True},{'actor_id':0},{'type_id':None},
    {'location':{'x':1,'y':2}},{'location':{'x':True,'y':2,'z':3}},{'yaw':float('inf')},
    {'unexpected':1}])
def test_invalid_review(changes):
    with pytest.raises(ValueError):validate_review(review()|changes)


def test_review_keeps_large_episode_exact_and_allows_rounding_and_wrapped_yaw():
    actor,current=fixture();current.location.x+=.001;current.rotation.yaw=-179.99
    verify_review(review(),2**64-1,actor,current)


@pytest.mark.parametrize('changes',[{'episode':'2'},{'actor_id':8},{'type_id':'vehicle.test'},
    {'location':{'x':1.1,'y':2,'z':3}},{'yaw':170.}])
def test_changed_world_actor_or_pose_rejected(changes):
    actor,current=fixture()
    with pytest.raises(ValueError):verify_review(review()|changes,2**64-1,actor,current)


def test_nonfinite_native_pose_rejected():
    actor,current=fixture();current.location.x=float('nan')
    with pytest.raises(ValueError):verify_review(review(),2**64-1,actor,current)


def test_bridge_does_not_mutate_stale_actor():
    actor,_=fixture();world=NS(id=2,get_actor=lambda _:actor)
    env=functions('update_actor',evaluation_active=lambda:False,connect_world=lambda:world)
    with pytest.raises(ValueError,match='World or actor changed'):
        env['update_actor'](7,{'location':{'x':10}},review())


def test_bridge_forwards_review_to_single_tick_owner():
    calls=[]
    env=functions('update_actor',evaluation_active=lambda:True,
        evaluation_command=lambda action,data:calls.append((action,data)) or {'ok':True})
    env['update_actor'](7,{'location':{'x':10}},review())
    assert calls[0][1]['expected']==review()


def test_evaluation_boundary_rejects_stale_pose_before_setter():
    path=Path(__file__).resolve().parents[1]/'src/carla_safety_agent/evaluation_control.py'
    cls=next(n for n in ast.parse(path.read_text()).body if isinstance(n,ast.ClassDef) and n.name=='EvaluationControl')
    method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='_execute')
    env={'Any':Any,'carla':NS(World=object),'__package__':'carla_safety_agent'}
    exec(compile(ast.Module(body=[method],type_ignores=[]),str(path),'exec'),env)
    actor,current=fixture();current.location.x=4
    with pytest.raises(ValueError,match='Actor moved'):
        env['_execute'](NS(),NS(id=2**64-1,get_actor=lambda _:actor),'update',
            {'actor_id':7,'transform':{'location':{'x':10}},'expected':review()})


def test_catalog_identity_keeps_episode_as_string():
    actor,current=fixture();current.rotation.pitch=0;current.rotation.roll=0
    actor.attributes={};actor.bounding_box=NS(extent=NS(x=1,y=1,z=1));actor.get_location=lambda:current.location
    env=functions('vector','actor_record',_origin_for_actor=lambda _:'user',_world_episode=2**64-1)
    assert env['actor_record'](actor)['edit_identity']=={'episode':str(2**64-1),'actor_id':7,'type_id':actor.type_id}

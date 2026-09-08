import ast
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import pytest


@pytest.mark.parametrize('sensor_attached,destroyed',[(True,True),(False,False),(False,True)])
def test_editor_delete_sensor_parent_and_native_failure(sensor_attached,destroyed):
    path=Path(__file__).resolve().parents[1]/'src/carla_safety_agent/evaluation_control.py'
    cls=next(n for n in ast.parse(path.read_text()).body if isinstance(n,ast.ClassDef) and n.name=='EvaluationControl')
    method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='_execute')
    env={'Any':Any,'carla':SimpleNamespace(World=object)}
    exec(compile(ast.Module(body=[method],type_ignores=[]),str(path),'exec'),env)
    calls=[]
    actor=SimpleNamespace(id=3,type_id='vehicle.test',destroy=lambda:calls.append(True) or destroyed)
    sensors=[SimpleNamespace(parent=actor)] if sensor_attached else []
    world=SimpleNamespace(get_actor=lambda identity:actor,get_actors=lambda:SimpleNamespace(filter=lambda pattern:sensors))
    control=SimpleNamespace(user_actor_ids={3})
    if sensor_attached or not destroyed:
        with pytest.raises(RuntimeError): env['_execute'](control,world,'delete',{'actor_id':3})
        assert control.user_actor_ids=={3}
    else:
        assert env['_execute'](control,world,'delete',{'actor_id':3})['actor_id']==3
        assert not control.user_actor_ids
    assert len(calls)==(0 if sensor_attached else 1)

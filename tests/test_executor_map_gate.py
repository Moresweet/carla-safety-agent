import ast
import __future__
import os
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from carla_safety_agent.carla_adapter import CarlaAdapter


@pytest.mark.parametrize('executor', ['native','rule'])
@pytest.mark.parametrize('busy', [False,True])
def test_worker_map_gate_and_wrong_load_fail_before_settings_write(tmp_path,executor,busy):
    calls=[]
    world=NS(get_settings=lambda:NS(synchronous_mode=busy),
             get_map=lambda:NS(name='Carla/Maps/Town04_Opt'),
             get_actors=lambda:NS(filter=lambda _:[]))
    def load(name):
        calls.append(name)
        return NS(get_map=lambda:NS(name='Carla/Maps/Town06'))
    client=NS(set_timeout=lambda _:None,get_world=lambda:world,load_world=load)
    carla=NS(Client=lambda *args:client)
    spec=NS(generated_map=None,map_name='Town04')
    if executor=='rule':
        instance=CarlaAdapter()
        instance._module=lambda:carla
        run=lambda:instance.run(spec,tmp_path)
    else:
        source=Path(__file__).resolve().parents[1]/'src/carla_safety_agent/native_executor.py'
        node=next(n for n in ast.parse(source.read_text()).body if isinstance(n,ast.ClassDef) and n.name=='NativeScenarioExecutor')
        env={'__package__':'carla_safety_agent','os':os,
             'read_verified_scenario':lambda *args:({},'digest'),
             'scenario_from_dict':lambda _:spec,
             'CarlaAdapter':lambda *args:NS(_module=lambda:carla)}
        exec(compile(ast.Module(body=[node],type_ignores=[]),str(source),'exec',
                     flags=__future__.annotations.compiler_flag),env)
        instance=env['NativeScenarioExecutor']()
        run=lambda:instance.run(tmp_path/'scenario.json',tmp_path/'agent.py','',tmp_path/'out.json')
    if busy:
        with pytest.raises(ValueError,match='synchronous owner'):run()
        assert calls==[]
    else:
        with pytest.raises(RuntimeError,match='requested map'):run()
        assert calls==['Town04']

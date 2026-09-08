"""Unit-test bridge contracts without importing the native CARLA extension."""
import ast
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def functions(*names, **environment):
    source = Path(__file__).resolve().parents[1] / 'tools/livery_bridge.py'
    tree = ast.parse(source.read_text())
    selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    environment.setdefault('simulation_operation', lambda function: function)
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(source), 'exec'), environment)
    return environment


def test_texture_identity_rejects_same_model_ambiguity():
    env = functions('runtime_name_for_actor', _actor_object_names={})
    world = SimpleNamespace(get_names_of_all_objects=lambda:['BP_TeslaM3_C_1','BP_TeslaM3_C_2'])
    actor = SimpleNamespace(id=7, type_id='vehicle.tesla.model3')
    with pytest.raises(RuntimeError, match='identity is unavailable'):
        env['runtime_name_for_actor'](world, actor)


def test_registered_texture_identity_is_exact():
    env = functions('runtime_name_for_actor', _actor_object_names={7:'BP_TeslaM3_C_1'})
    world = SimpleNamespace(get_names_of_all_objects=lambda:['BP_TeslaM3_C_1','BP_TeslaM3_C_2'])
    actor = SimpleNamespace(id=7, type_id='vehicle.tesla.model3')
    assert env['runtime_name_for_actor'](world, actor) == 'BP_TeslaM3_C_1'


def test_actor_record_keeps_rotation_and_origin():
    env = functions('vector', 'actor_record', _origin_for_actor=lambda actor: 'user')
    vector = SimpleNamespace(x=1,y=2,z=3)
    actor = SimpleNamespace(id=7,type_id='static.prop.advertisement',attributes={},
        bounding_box=SimpleNamespace(extent=vector),get_location=lambda:vector,
        get_transform=lambda:SimpleNamespace(rotation=SimpleNamespace(pitch=0,yaw=35,roll=0)))
    record = env['actor_record'](actor)
    assert record['origin'] == 'user'
    assert record['kind'] == 'prop'
    assert record['rotation']['yaw'] == 35


def test_generation_does_not_compete_with_evaluation():
    env = functions('compile_scenario', evaluation_active=lambda:True)
    with pytest.raises(RuntimeError, match='Stop the closed-loop'):
        env['compile_scenario']({}, True)


def test_initializing_evaluation_never_reads_world():
    env = functions('scene_state', evaluation_active=lambda: True,
                    evaluation_snapshot=lambda: None, _scene_snapshot=None,
                    RUNTIME_MODE='native')
    assert env['scene_state']()['initializing']


def test_direct_rpc_is_blocked_during_evaluation():
    import threading
    env = functions('connect_world', evaluation_active=lambda: True,
                    _simulation_lock=threading.RLock())
    with pytest.raises(RuntimeError, match='owns CARLA'):
        env['connect_world']()


def test_client_is_reused():
    import threading
    clients = []
    world = SimpleNamespace(id=1)
    def client(*args):
        clients.append(args)
        return SimpleNamespace(set_timeout=lambda value: None, get_world=lambda: world)
    env = functions('connect_world', evaluation_active=lambda: False,
                    _simulation_lock=threading.RLock(), _carla_client=None, _world_episode=1,
                    carla=SimpleNamespace(Client=client), HOST='localhost', CARLA_PORT=2000)
    assert env['connect_world']() is env['connect_world']() is world
    assert len(clients) == 1


def test_stop_does_not_interrupt_cleanup_twice():
    import threading
    env = functions('stop_e2e', _e2e_lock=threading.Lock(), _e2e_job={'state': 'stopping'})
    assert env['stop_e2e']() == {'ok': True, 'state': 'stopping'}


@pytest.mark.parametrize('state,code,expected', [('running', 0, 'succeeded'),
                                              ('stopping', 1, 'stopped')])
def test_non_route_completion_and_user_stop(tmp_path, state, code, expected):
    import threading
    import time
    process = SimpleNamespace(pid=123, wait=lambda: code)
    pid = tmp_path/'pid'
    pid.write_text('123')
    job = {'state': state, 'results': None}
    env = functions('_finish_e2e', _e2e_pid=pid, _e2e_process=process,
                    _e2e_lock=threading.Lock(), _e2e_job=job, Path=Path, time=time,
                    SESSION=SimpleNamespace(transition=lambda *args, **kwargs: None))
    env['_finish_e2e'](process)
    assert job['state'] == expected
    assert not pid.exists()


def test_natural_language_evaluation_uses_supported_model():
    calls = []
    env = functions('evaluate_scenario', compile_scenario=lambda data: {'scenario_path': '/test.json'},
                    start_e2e=lambda data: calls.append(data) or {'ok': True})
    assert env['evaluate_scenario']({})['evaluation']['ok']
    assert calls[0]['algorithm'] == 'uniad-tiny'


def test_simulation_handoff_waits_for_editor_operation():
    import threading
    from functools import wraps
    env = functions('simulation_operation', wraps=wraps, _simulation_lock=threading.RLock())
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    @env['simulation_operation']
    def editor():
        entered.set()
        assert release.wait(2)
    @env['simulation_operation']
    def handoff():
        finished.set()
    first = threading.Thread(target=editor)
    second = threading.Thread(target=handoff)
    first.start()
    assert entered.wait(1)
    second.start()
    assert not finished.wait(.05)
    release.set()
    first.join(2)
    second.join(2)
    assert finished.is_set()


def test_cancel_during_initialization_is_not_lost():
    path = Path(__file__).resolve().parents[1]/'integration/bench2drive/leaderboard_evaluator.py'
    tree = ast.parse(path.read_text())
    node = next(n for n in tree.body if isinstance(n, ast.ClassDef))
    class Base:
        def __init__(self):
            self.manager = SimpleNamespace(_running=False)
            self.module_agent = SimpleNamespace(get_entry_point=lambda: 'Agent', Agent=object)
        def _signal_handler(self, signum, frame):
            self.manager._running = False
        def _cleanup(self):
            calls.append('upstream')
    calls = []
    env = {'upstream': SimpleNamespace(LeaderboardEvaluator=Base)}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), env)
    evaluator = env['CancellationSafeEvaluator']()
    with pytest.raises(KeyboardInterrupt):
        evaluator._signal_handler(2, None)
    evaluator.manager._running = True
    evaluator._signal_handler(2, None)
    assert not evaluator.manager._running
    evaluator.agent_instance = SimpleNamespace(_capture=SimpleNamespace(close=lambda: calls.append('capture')))
    evaluator._cleanup()
    assert calls == ['capture', 'upstream']
    assert evaluator.agent_instance._capture is None


def test_benchmark_failure_is_not_hidden_by_zero_exit(tmp_path):
    result = tmp_path / 'result.json'
    result.write_text(json.dumps({'_checkpoint': {
        'global_record': {'status': 'Failed'},
        'records': [{'status': 'Failed - Agent crashed'}],
    }}))
    env = functions('_benchmark_result_failed', Path=Path, json=json)
    assert env['_benchmark_result_failed'](result)
    result.write_text(json.dumps({'_checkpoint': {
        'global_record': {'status': 'Completed'},
        'records': [{'status': 'Completed'}],
    }}))
    assert not env['_benchmark_result_failed'](result)


def test_evaluation_texture_does_not_match_actor_id_in_lamppost_name():
    import __future__
    source = Path(__file__).resolve().parents[1] / 'src/carla_safety_agent/evaluation_control.py'
    tree = ast.parse(source.read_text())
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_runtime_vehicle_name')
    env = {}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), 'exec',
                 flags=__future__.annotations.compiler_flag), env)
    actor = SimpleNamespace(id=173,type_id='vehicle.lincoln.mkz_2020')
    world = SimpleNamespace(get_names_of_all_objects=lambda:['BP_Lamppost_tall15_173','BP_Lincoln2020_C_0'],
        get_actors=lambda:SimpleNamespace(filter=lambda pattern:[actor]))
    assert env['_runtime_vehicle_name'](world,actor) == 'BP_Lincoln2020_C_0'
    world.get_names_of_all_objects = lambda:['BP_Lamppost_tall15_173']
    with pytest.raises(RuntimeError, match='ambiguous'):
        env['_runtime_vehicle_name'](world,actor)

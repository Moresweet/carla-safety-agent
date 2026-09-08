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


@pytest.mark.parametrize('slot', [True, -1, 1.5, '1.5', '', '0|apply'])
def test_material_slot_rejects_non_integral_index(slot):
    env = functions('apply_material_slot', material_catalog=lambda _: {'target': 'house'})
    with pytest.raises(ValueError, match='non-negative integer'):
        env['apply_material_slot']({'object_id': 1, 'component': 'mesh', 'slot': slot})


def test_material_restore_targets_only_verified_component_slot():
    calls = []
    world = SimpleNamespace(id=7, apply_color_texture_to_object=lambda *args: calls.append(args))
    env = functions('apply_material_slot',
        material_catalog=lambda _: {'target': 'house', 'components': [
            {'component': 'mesh', 'slots': [{'slot': 2, 'status': 'uv0_ready'}]}]},
        connect_world=lambda: world,
        carla=SimpleNamespace(TextureColor=lambda *args: 'empty',
                              MaterialParameter=SimpleNamespace(Diffuse='diffuse')),
        MATERIALS=SimpleNamespace(record=lambda *args: calls.append(args)))
    result = env['apply_material_slot']({'object_id': 1, 'component': 'mesh', 'slot': '2'})
    assert calls == [('house|csa|mesh|2|restore', 'diffuse', 'empty'),
                     (7, 'house', 'mesh', 2, None)]
    assert result['operation'] == 'restore'
    with pytest.raises(ValueError, match='verified UV0'):
        env['apply_material_slot']({'object_id': 1, 'component': 'other', 'slot': 2})
    assert len(calls) == 2


def test_material_http_routes_and_body_limit():
    import io
    from urllib.parse import urlparse, parse_qs
    source = Path(__file__).resolve().parents[1] / 'tools/livery_bridge.py'
    node = next(n for n in ast.parse(source.read_text()).body
                if isinstance(n, ast.ClassDef) and n.name == 'Handler')
    calls = []
    env = {'BaseHTTPRequestHandler': object, 'urlparse': urlparse, 'parse_qs': parse_qs,
           'json': json, 'apply_material_slot': lambda data, payload=None:
           calls.append((data, payload)) or {'ok': True}}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), 'exec'), env)
    handler = env['Handler']()
    statuses = []
    handler._headers = lambda status=200: statuses.append(status)
    handler.path = '/materials/apply?object_id=1&component=mesh&slot=2'
    handler.headers = {'Content-Length': '3'}
    handler.rfile, handler.wfile = io.BytesIO(b'png'), io.BytesIO()
    handler.do_POST()
    assert statuses == [200]
    assert calls == [({'object_id': '1', 'component': 'mesh', 'slot': '2'}, b'png')]
    handler.headers = {'Content-Length': str(17 * 1024 * 1024)}
    handler.rfile = io.BytesIO(b'unread')
    handler.do_POST()
    assert statuses[-1] == 413 and handler.rfile.tell() == 0
    assert len(calls) == 1


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


def test_evaluation_visibility_uses_same_durable_store(tmp_path):
    import __future__
    from carla_safety_agent.visibility import VisibilityStore
    source = Path(__file__).resolve().parents[1]/'src/carla_safety_agent/evaluation_control.py'
    node = next(n for n in ast.parse(source.read_text()).body if isinstance(n, ast.ClassDef))
    env = {'ENVIRONMENT_LABELS':{'buildings':'building'}, '_vector':lambda _: {'x':0,'y':0,'z':0}}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), 'exec',
                 flags=__future__.annotations.compiler_flag), env)
    controller = object.__new__(env['EvaluationControl'])
    controller.visibility = VisibilityStore(tmp_path)
    obj = SimpleNamespace(id=17,name='House',bounding_box=SimpleNamespace(location=None,extent=None),
                          transform=SimpleNamespace(rotation=SimpleNamespace(pitch=0,yaw=0,roll=0)))
    calls = []
    world = SimpleNamespace(id=3,get_environment_objects=lambda _: [obj],
                            enable_environment_objects=lambda ids,value: calls.append((ids,value)))
    controller._execute(world,'environment_visibility',{'object_id':17,'visible':False})
    listing = controller._execute(world,'catalog_environment',{'category':'buildings'})
    assert listing['objects'][0]['visible'] is False
    assert VisibilityStore(tmp_path).records(3) == [{'object_id':'17','name':'House'}]
    with pytest.raises(ValueError):
        controller._execute(world,'environment_visibility',{'object_id':17,'visible':'false'})
    assert calls == [({17},False)]


def test_restore_unknown_weather_is_rejected_before_any_world_mutation():
    from carla_safety_agent.scene_store import validate_scene
    calls = []
    world = SimpleNamespace(id=1, get_map=lambda:SimpleNamespace(name='Town04'),
        get_blueprint_library=lambda:SimpleNamespace(find=lambda _: None),
        get_weather=lambda:SimpleNamespace(wetness=0),
        get_spectator=lambda:SimpleNamespace(get_transform=lambda:None),
        set_weather=lambda _:calls.append('weather'))
    document = {'map':'Town04','objects':[{'stable_id':'new','blueprint_id':'static.prop.box01',
        'transform':{'location':{'x':1,'y':1,'z':1},'rotation':{'yaw':0,'pitch':0,'roll':0}}}],
        'weather':{'unsupported_weather':1}}
    env = functions('restore_scene', connect_world=lambda:world,
        SCENES=SimpleNamespace(read=lambda *args:{'document':document}), validate_scene=validate_scene,
        BLENDER=SimpleNamespace(registry=lambda:{}), _provenance=SimpleNamespace(records=lambda _:{}),
        prepare_scene_materials=lambda *args:None, prepare_scene_visibility=lambda *args:None,
        spawn_object=lambda *args:calls.append('spawn'), update_actor=lambda *args:calls.append('move'))
    with pytest.raises(ValueError, match='Unsupported weather'):
        env['restore_scene']({'scene_id':'test'})
    assert calls == []


def test_capture_stop_cannot_stop_a_new_or_model_session():
    import threading
    calls = []
    current = {'kind':'sensor-rig','run_id':'new'}
    env = functions('stop_sensor_rig', _e2e_lock=threading.RLock(),
                    SESSION=SimpleNamespace(snapshot=lambda:current),
                    stop_e2e=lambda:calls.append('stop') or {'ok':True})
    with pytest.raises(ValueError): env['stop_sensor_rig']({'run_id':'old'})
    current['kind']='preset-run'
    with pytest.raises(ValueError): env['stop_sensor_rig']({'run_id':'new'})
    assert calls == []
    current['kind']='sensor-rig'
    assert env['stop_sensor_rig']({'run_id':'new'})['ok']


def test_bridge_execution_lock_allows_capture_start_reentry():
    import threading
    source=Path(__file__).resolve().parents[1]/'tools/livery_bridge.py'
    node=next(n for n in ast.parse(source.read_text()).body if isinstance(n,ast.Assign)
              and any(isinstance(t,ast.Name) and t.id=='_e2e_lock' for t in n.targets))
    env={'threading':threading}
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(source),'exec'),env)
    lock=env['_e2e_lock']
    with lock:
        assert lock.acquire(blocking=False), 'Starting collection must not deadlock itself'
        lock.release()


@pytest.mark.parametrize('exited', [False, True])
def test_failed_start_keeps_waiter_and_only_signals_live_child(exited):
    import signal
    calls = []
    process = SimpleNamespace(pid=123, poll=lambda:0 if exited else None)
    job = {'kind':'sensor-rig'}
    env = functions('_abort_e2e_start', _e2e_job=job, signal=signal,
        os=SimpleNamespace(killpg=lambda pid,sig:calls.append(('signal',pid,sig))),
        threading=SimpleNamespace(Thread=lambda **kwargs:SimpleNamespace(start=lambda:calls.append(('wait',kwargs['args'])))),
        _finish_e2e=lambda _:None)
    env['_abort_e2e_start'](process, OSError('disk full'))
    assert job['state']=='running' and job['startup_error']=='disk full'
    assert calls[-1]==('wait',(process,))
    assert len(calls)==(1 if exited else 2)


def test_failed_start_cannot_be_reported_completed(tmp_path):
    import threading
    import time
    calls = []
    process = SimpleNamespace(pid=123,wait=lambda:0)
    job = {'kind':'sensor-rig','state':'running','startup_error':'disk full'}
    env = functions('_finish_e2e', _e2e_process=process, _e2e_job=job,
        SESSION=SimpleNamespace(transition=lambda state,**kw:calls.append((state,kw))),
        restore_editor_world=lambda:calls.append(('restore',{})),
        _e2e_pid=tmp_path/'pid', _e2e_lock=threading.RLock(), Path=Path,time=time)
    env['_finish_e2e'](process)
    assert calls[1][0]=='restore'
    assert calls[-1][0]=='failed'
    assert calls[-1][1]['error']=='disk full'
    assert calls[-1][1]['outcome']['failure_category']=='startup'
    assert job['state']=='failed'


def test_failed_start_signal_error_still_installs_waiter():
    import signal
    calls = []
    def denied(*args):
        raise PermissionError('signal denied')
    env = functions('_abort_e2e_start', _e2e_job={}, signal=signal,
        os=SimpleNamespace(killpg=denied),
        threading=SimpleNamespace(Thread=lambda **kwargs:SimpleNamespace(start=lambda:calls.append('wait'))),
        _finish_e2e=lambda _:None)
    with pytest.raises(PermissionError):
        env['_abort_e2e_start'](SimpleNamespace(pid=123,poll=lambda:None),'startup error')
    assert calls==['wait']


def test_journal_failure_does_not_skip_world_recovery(tmp_path):
    import threading
    import time
    calls = []
    def transition(*args,**kwargs):
        raise OSError('disk full')
    process = SimpleNamespace(pid=123,wait=lambda:1)
    env = functions('_finish_e2e', _e2e_process=process,
        _e2e_job={'kind':'sensor-rig','state':'running'},
        SESSION=SimpleNamespace(transition=transition),
        restore_editor_world=lambda:calls.append('restore'),
        _e2e_pid=tmp_path/'pid', _e2e_lock=threading.RLock(), Path=Path,time=time)
    with pytest.raises(OSError,match='disk full'):
        env['_finish_e2e'](process)
    assert calls==['restore']


def test_manual_control_rejects_other_sessions_and_uses_server_time(tmp_path):
    import threading
    current={'state':'running','kind':'sensor-rig','run_id':'run',
             'configuration':{'request':{'mode':'manual'}}}
    env=functions('manual_sensor_control',_e2e_lock=threading.RLock(),
        SESSION=SimpleNamespace(snapshot=lambda:current,owned_pid=lambda:123),
        time=SimpleNamespace(monotonic=lambda:42),_evaluation_control_dir=tmp_path)
    with pytest.raises(ValueError): env['manual_sensor_control']({'run_id':'old','control':{}})
    assert not (tmp_path/'manual-control.json').exists()
    env['manual_sensor_control']({'run_id':'run','issued_monotonic':999,'control':{'throttle':.2}})
    command=json.loads((tmp_path/'manual-control.json').read_text())
    assert command['issued_monotonic']==42 and command['execution_id']=='run'
    for mode in ('autopilot','stationary'):
        current['configuration']['request']['mode']=mode
        with pytest.raises(ValueError): env['manual_sensor_control']({'run_id':'run','control':{}})


def test_starting_scene_snapshot_includes_managed_state_without_saving_version():
    weather=SimpleNamespace(**{k:0 for k in ('cloudiness','precipitation','precipitation_deposits',
        'wind_intensity','sun_azimuth_angle','sun_altitude_angle','fog_density','fog_distance','wetness')})
    world=SimpleNamespace(id=7,get_actors=lambda:[],get_weather=lambda:weather,
        get_map=lambda:SimpleNamespace(name='Town04'),
        get_spectator=lambda:SimpleNamespace(get_transform=lambda:'pose'))
    env=functions('capture_scene_document',connect_world=lambda:world,
        _provenance=SimpleNamespace(records=lambda _:{}),
        MATERIALS=SimpleNamespace(overrides=lambda _:{'slot':{'texture':'hash'}}),
        VISIBILITY=SimpleNamespace(records=lambda _:[{'object_id':'1','name':'wall'}]),
        transform_record=lambda value:value)
    result=env['capture_scene_document']()
    assert result['map']=='Town04' and result['spectator']=='pose'
    assert result['environment_materials']==[{'texture':'hash'}]
    assert result['hidden_environment'][0]['object_id']=='1'
    assert result['limitations'] and 'version' not in result

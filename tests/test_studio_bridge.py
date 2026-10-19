"""Unit-test bridge contracts without importing the native CARLA extension."""
import ast
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def functions(*names, **environment):
    if 'actor_material_history_action' in names or 'recover_actor_material_history' in names:
        names=(*names,'actor_material_history_callbacks')
    if 'delete_actor' in names:
        names = (*names, 'confirm_actor_deletion')
    if 'restore_scene' in names:
        names = (*names, 'restore_scene_document')
    source = Path(__file__).resolve().parents[1] / 'tools/livery_bridge.py'
    tree = ast.parse(source.read_text())
    selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    environment.setdefault('simulation_operation', lambda function: function)
    environment.setdefault('journal_duplicate', lambda function: function)
    environment.setdefault('MATERIAL_HISTORY', SimpleNamespace(execute=lambda identity,before,after,apply: (apply(),'test-operation')[1]))
    environment.setdefault('HANDOFF',SimpleNamespace(require_idle=lambda:None))
    environment.setdefault('require_simulator_connection', lambda host, port: None)
    environment.setdefault('HOST', '127.0.0.1')
    environment.setdefault('CARLA_PORT', 2000)
    environment.setdefault('backup_managed_deletion', lambda *_:None)
    environment.setdefault('copy_duplicate_materials', lambda *_:None)
    environment.setdefault('preflight_duplicate_materials', lambda *_:None)
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(source), 'exec'), environment)
    return environment


def test_actor_recovery_requires_confirmation_and_idle_world(monkeypatch):
    calls=[]
    monkeypatch.setattr('carla_safety_agent.world_readiness.require_idle_native_world',lambda world:(_ for _ in ()).throw(ValueError('Native world busy')))
    env=functions('recover_actor_material_history',evaluation_active=lambda:False,connect_world=lambda:object(),
        ACTOR_MATERIAL_HISTORY=SimpleNamespace(recover=lambda *args:calls.append(args)))
    payload=dict(operation_id='op',inspection_token='a'*64,choice='source',registered_texture=None,confirmed=True)
    with pytest.raises(ValueError,match='Explicit'):env['recover_actor_material_history']({**payload,'confirmed':False})
    with pytest.raises(ValueError,match='Native world busy'):env['recover_actor_material_history'](payload)
    assert calls==[]


@pytest.mark.parametrize('inspection',[False,True])
@pytest.mark.parametrize('changed',['none','episode','missing','blueprint','stable','origin','texture','active'])
def test_actor_material_transition_checks_live_identity(tmp_path,changed,inspection):
    from carla_safety_agent.actor_material_history import ActorMaterialHistory,apply_with_history
    identity=dict(episode='1',actor_id=2,stable_id='stable-a',blueprint_id='vehicle.audi.a2',component='VehicleMesh',slot=4)
    history=ActorMaterialHistory(tmp_path/'history')
    operation=apply_with_history(history.root,identity,None,'a'*64,SimpleNamespace(apply=lambda:None))
    actor=SimpleNamespace(id=2,type_id='other' if changed=='blueprint' else 'vehicle.audi.a2')
    record=dict(origin='scene' if changed=='origin' else 'user',stable_id='other' if changed=='stable' else 'stable-a',type_id='vehicle.audi.a2',
        actor_materials=[dict(component='VehicleMesh',slot=4,texture=('b' if changed=='texture' else 'a')*64)])
    world=SimpleNamespace(id=9 if changed=='episode' else 1,get_actor=lambda _:None if changed=='missing' else actor)
    calls=[]
    def prepare(world,document,live,provenance):
        assert document['actor_materials']==[]
        return SimpleNamespace(apply=lambda:calls.append('apply'))
    env=functions('actor_material_history_action','inspect_actor_material_history',ACTOR_MATERIAL_HISTORY=history,
        evaluation_active=lambda:changed=='active',connect_world=lambda:world,
        _provenance=SimpleNamespace(records=lambda _:{'2':record}),prepare_scene_actor_materials=prepare)
    request=dict(operation_id=operation,direction='undo',revision=operation,confirmed=True)
    if inspection:
        before=history.path(operation).read_bytes()
        if changed in ('none','texture'):
            result=env['inspect_actor_material_history'](operation)
            assert result['registry_matches']==('target' if changed=='none' else 'neither')
            assert result['native_verified'] is False
        else:
            with pytest.raises(ValueError):env['inspect_actor_material_history'](operation)
        assert calls==[] and history.path(operation).read_bytes()==before
        return
    if changed=='none':
        result=env['actor_material_history_action'](request)
        assert result['applied'] is False and result['revision']!=operation and calls==['apply']
    else:
        with pytest.raises(ValueError):env['actor_material_history_action'](request)
        assert calls==[] and 'pending' not in history.read(operation)


def test_duplicate_journal_decorator_records_exact_source_and_target(tmp_path):
    from carla_safety_agent.copy_history import CopyHistory
    from carla_safety_agent.editor_history import editor_history
    from carla_safety_agent.transform_history import TransformHistory
    from carla_safety_agent.deletion_history import DeletionHistory
    store=CopyHistory(tmp_path/'copies')
    world=SimpleNamespace(id=1,get_actor=lambda actor_id:SimpleNamespace(id=actor_id,type_id='prop.test'))
    target=dict(episode='1',actor_id=8,type_id='prop.test',stable_id='new-object')
    env=functions('journal_duplicate',evaluation_active=lambda:False,connect_world=lambda:world,
        _provenance=SimpleNamespace(records=lambda _:{}),COPY_HISTORY=store,
        position_history_identity=lambda *_:target)
    calls=[]
    wrapped=env['journal_duplicate'](lambda actor_id:calls.append(actor_id) or {'object':{'id':8}})
    result=wrapped(7)
    row=store.read(result['copy_operation_id'])
    assert calls==[7] and row['identity']['actor_id']==7 and row['target']==target
    combined=editor_history(TransformHistory(tmp_path/'moves'),DeletionHistory(tmp_path/'deletes'),copies=store)
    assert combined['entries']==[row] and combined['complete']


def test_copy_undo_bridge_checks_review_and_only_deletes_target(tmp_path):
    from carla_safety_agent.copy_history import CopyHistory
    store=CopyHistory(tmp_path/'copies')
    source=dict(episode='1',actor_id=7,type_id='prop.test',stable_id='source')
    target={**source,'actor_id':8,'stable_id':'target'}
    operation=store.execute(source,lambda:{'object':{'id':8}},lambda _:target)['copy_operation_id']
    pose=SimpleNamespace(location=SimpleNamespace(x=1,y=2,z=3),rotation=SimpleNamespace(yaw=0))
    actor=SimpleNamespace(id=8,type_id='prop.test',get_transform=lambda:pose)
    calls=[]
    env=functions('undo_copy',COPY_HISTORY=store,evaluation_active=lambda:False,
        connect_world=lambda:SimpleNamespace(id=1,get_actor=lambda actor_id:actor if actor_id==8 else None),
        position_history_identity=lambda *_:target,
        delete_actor=lambda actor_id:calls.append(actor_id) or {'ok':True,'actor_id':actor_id,'backup':{'stable_id':'target'},'operation_id':'deletion'})
    review=dict(episode='1',actor_id=8,type_id='prop.test',location=dict(x=1,y=2,z=3),yaw=0)
    request=dict(operation_id=operation,review=review,confirmed=True)
    with pytest.raises(ValueError,match='moved'):
        env['undo_copy']({**request,'review':{**review,'location':dict(x=9,y=2,z=3)}})
    assert calls==[]
    assert env['undo_copy'](request)['ok'] and calls==[8]


@pytest.mark.parametrize('data', [None, {}, {'recording':'false'}, {'recording':1},
    {'recording':True,'every':True}, {'recording':True,'every':1.5},
    {'recording':True,'every':0}, {'recording':True,'every':101},
    {'recording':True,'max_frames':'3'}, {'recording':True,'max_frames':0},
    {'recording':True,'max_frames':10001}, {'recording':False,'control':{}}])
def test_recording_request_rejects_invalid_input_without_writing(tmp_path, data):
    env=functions('collection_request', _evaluation_control_dir=tmp_path)
    with pytest.raises(ValueError):
        env['collection_request'](data)
    assert not list(tmp_path.iterdir())


def test_recording_request_preserves_exact_limits(tmp_path):
    import uuid
    env=functions('collection_request', _evaluation_control_dir=tmp_path,
                  evaluation_active=lambda:True, uuid=uuid, json=json,
                  SESSION=SimpleNamespace(snapshot=lambda:{'run_id':'execution-a'}))
    result=env['collection_request']({'recording':True,'every':1,'max_frames':3})
    saved=json.loads((tmp_path/'collection-request.json').read_text())
    assert saved==result['request']
    assert saved['recording'] is True and saved['every']==1 and saved['max_frames']==3
    assert saved['execution_id']=='execution-a'


@pytest.mark.parametrize('run_id,state,owned', [('old','running',True),('current','stopped',True),('current','running',False)])
def test_recording_control_refuses_wrong_or_dead_execution(run_id,state,owned):
    import threading
    env=functions('recording_control', _e2e_lock=threading.RLock(),
        SESSION=SimpleNamespace(snapshot=lambda:{'run_id':'current','state':state,'kind':'preset-run'},owned_pid=lambda:owned),
        collection_request=lambda _:pytest.fail('Unexpected write'))
    with pytest.raises(ValueError,match='matching live'):
        env['recording_control']({'run_id':run_id,'recording':True})


def test_recording_control_writes_under_session_lock():
    import threading
    lock=threading.RLock()
    def write(data):
        assert lock._is_owned()
        assert data=={'recording':False}
        return {'ok':True}
    env=functions('recording_control', _e2e_lock=lock,
        SESSION=SimpleNamespace(snapshot=lambda:{'run_id':'current','state':'running','kind':'preset-run'},owned_pid=lambda:123),
        collection_request=write)
    assert env['recording_control']({'run_id':'current','recording':False})=={'ok':True}


@pytest.mark.parametrize('data', [None, {}, {'confirmed': False},
    {'scene_id':'s','version':'v','stable_id':'a','confirmed':True,'extra':1}])
def test_single_object_restore_requires_exact_confirmation(data):
    env=functions('restore_missing_object')
    with pytest.raises(ValueError,match='Confirm an exact'):
        env['restore_missing_object'](data)


def test_single_object_restore_rejects_running_evaluation_before_world_access():
    env=functions('restore_missing_object',evaluation_active=lambda:True)
    with pytest.raises(ValueError,match='Stop evaluation'):
        env['restore_missing_object']({'scene_id':'s','version':'v','stable_id':'a','confirmed':True})


def test_single_object_restore_never_overwrites_existing_stable_identity(monkeypatch):
    import carla_safety_agent.world_readiness as readiness
    monkeypatch.setattr(readiness, 'require_idle_native_world', lambda _: None)
    pose={'location':dict(x=0,y=0,z=1),'rotation':dict(pitch=0,yaw=0,roll=0)}
    document={'map':'Town04','objects':[{'stable_id':'a','blueprint_id':'static.prop.advertisement','transform':pose}]}
    def forbidden(*_):
        pytest.fail('Existing object must not enter restore mutation')
    env=functions('restore_missing_object', evaluation_active=lambda:False,
        require_asset_import_idle=lambda:None, connect_world=lambda:SimpleNamespace(id=1),
        SCENES=SimpleNamespace(read=lambda *_:{'document':document}),
        _provenance=SimpleNamespace(records=lambda _:{}),
        live_scene_bindings=lambda *_:{'a':object()}, restore_scene_document=forbidden)
    with pytest.raises(ValueError,match='already exists'):
        env['restore_missing_object']({'scene_id':'s','version':'v','stable_id':'a','confirmed':True})


def test_deletion_intent_write_failure_prevents_native_destroy():
    actor=SimpleNamespace(type_id='static.prop.test',destroy=lambda:pytest.fail('must not destroy'))
    world=SimpleNamespace(id=1,get_actor=lambda _:actor)
    def fail(*_):raise OSError('disk full')
    env=functions('delete_actor',evaluation_active=lambda:False,connect_world=lambda:world,
                  backup_managed_deletion=lambda *_:{'scene_id':'s'},
                  DELETION_HISTORY=SimpleNamespace(begin=fail))
    with pytest.raises(OSError,match='disk full'):env['delete_actor'](7)


def test_deletion_uncertainty_persists_backup_link(tmp_path):
    from carla_safety_agent.deletion_history import DeletionHistory
    history=DeletionHistory(tmp_path/'history')
    actor=SimpleNamespace(type_id='static.prop.test',destroy=lambda:True)
    world=SimpleNamespace(id=1,get_actor=lambda _:actor,wait_for_tick=lambda _:None)
    backup=dict(scene_id='scene',version='version',stable_id='stable')
    env=functions('delete_actor',evaluation_active=lambda:False,connect_world=lambda:world,
                  backup_managed_deletion=lambda *_:backup,DELETION_HISTORY=history)
    with pytest.raises(RuntimeError,match='requires inspection'):env['delete_actor'](7)
    rows=list(history.root.glob('*.json'))
    assert len(rows)==1
    row=json.loads(rows[0].read_text())
    assert row['state']=='needs_attention' and row['backup']==backup


@pytest.mark.parametrize('after_replace',[False,True])
def test_delete_completion_storage_failure_never_returns_success(tmp_path,monkeypatch,after_replace):
    import carla_safety_agent.deletion_history as module
    history=module.DeletionHistory(tmp_path/'history')
    original=module.atomic
    def fail_confirmation(path,row):
        if row['state']=='confirmed':
            if after_replace:original(path,row)
            raise OSError('confirmation persistence failure')
        original(path,row)
    monkeypatch.setattr(module,'atomic',fail_confirmation)
    destroyed=[]
    actor=SimpleNamespace(type_id='static.prop.test',destroy=lambda:destroyed.append(7) or True)
    world=SimpleNamespace(id=1,get_actor=lambda _:actor,
                          wait_for_tick=lambda _:SimpleNamespace(find=lambda _:None))
    backup=dict(scene_id='scene',version='version',stable_id='stable')
    env=functions('delete_actor',evaluation_active=lambda:False,connect_world=lambda:world,
                  backup_managed_deletion=lambda *_:backup,DELETION_HISTORY=history,
                  _actor_object_names={},_generated_actor_assets={},_editor_actors={7})
    with pytest.raises(RuntimeError,match='requires inspection'):env['delete_actor'](7)
    assert destroyed==[7]
    row=history.list()['entries'][0]
    assert row['state']==('confirmed' if after_replace else 'needs_attention')
    assert row['backup']==backup


@pytest.mark.parametrize('present,same_map',[(True,True),(False,True),(False,False)])
def test_deletion_inspection_is_read_only(monkeypatch,present,same_map):
    import carla_safety_agent.world_readiness as readiness
    monkeypatch.setattr(readiness,'require_idle_native_world',lambda _:None)
    actor=SimpleNamespace(id=22,type_id='static.prop.test')
    world=SimpleNamespace(id=2,get_map=lambda:SimpleNamespace(name='Town04'))
    row={'state':'attempting','episode':1,'type_id':'static.prop.test',
         'backup':dict(scene_id='s',version='v',stable_id='stable')}
    env=functions('inspect_deletion',DELETION_HISTORY=SimpleNamespace(read=lambda _:row),
        evaluation_active=lambda:False,require_asset_import_idle=lambda:None,connect_world=lambda:world,
        SCENES=SimpleNamespace(read=lambda *_:{'document':{'map':'Town04' if same_map else 'Town05'}}),
        _provenance=SimpleNamespace(records=lambda _:{}),
        live_scene_bindings=lambda *_:{'stable':actor} if present else {})
    result=env['inspect_deletion']('op')
    assert result['observation']==('different_map' if not same_map else 'present' if present else 'missing')
    assert result['actor_id']==(22 if present else None)
    assert result['same_episode'] is False and row['state']=='attempting'


def test_deletion_inspection_rejects_running_evaluation():
    env=functions('inspect_deletion',DELETION_HISTORY=SimpleNamespace(read=lambda _:{}),evaluation_active=lambda:True)
    with pytest.raises(ValueError,match='Stop evaluation'):env['inspect_deletion']('op')


def test_duplicate_uses_durable_generated_blueprint_and_options():
    record={'type_id':'static.prop.mesh','blueprint_id':'generated.test','spawn_options':{'scale':42,'mass':3}}
    env=functions('duplicate_spawn_spec',_provenance=SimpleNamespace(records=lambda _:{'7':record}),_generated_actor_assets={})
    blueprint,options=env['duplicate_spawn_spec'](SimpleNamespace(id=1),SimpleNamespace(id=7,type_id='static.prop.mesh'))
    assert blueprint=='generated.test' and options=={'scale':42,'mass':3}
    options['scale']=10
    assert record['spawn_options']['scale']==42


@pytest.mark.parametrize('options',[{'scale':0},{'scale':True},{'mass':-1},{'mass':float('nan')},{'unknown':1}])
def test_duplicate_rejects_invalid_recorded_options(options):
    record={'type_id':'static.prop.mesh','blueprint_id':'generated.test','spawn_options':options}
    env=functions('duplicate_spawn_spec',_provenance=SimpleNamespace(records=lambda _:{'7':record}),_generated_actor_assets={})
    with pytest.raises(ValueError):env['duplicate_spawn_spec'](SimpleNamespace(id=1),SimpleNamespace(id=7,type_id='static.prop.mesh'))


def test_duplicate_refuses_mesh_without_asset_identity():
    env=functions('duplicate_spawn_spec',_provenance=SimpleNamespace(records=lambda _:{}),_generated_actor_assets={})
    with pytest.raises(ValueError,match='identity missing'):
        env['duplicate_spawn_spec'](SimpleNamespace(id=1),SimpleNamespace(id=7,type_id='static.prop.mesh'))


def test_duplicate_forwards_options_without_source_stable_id():
    pose=SimpleNamespace(location=10,rotation=SimpleNamespace(pitch=0,yaw=20,roll=0),
                         get_right_vector=lambda:1,get_forward_vector=lambda:1)
    actor=SimpleNamespace(type_id='static.prop.mesh',get_transform=lambda:pose,
                          bounding_box=SimpleNamespace(extent=SimpleNamespace(x=1,y=1)))
    calls=[]
    env=functions('duplicate_actor',evaluation_active=lambda:False,
        connect_world=lambda:SimpleNamespace(get_actor=lambda _:actor),
        duplicate_spawn_spec=lambda *_:('generated.test',{'mass':3,'scale':42}),
        vector=lambda n:{'x':n,'y':0,'z':1},
        spawn_object=lambda blueprint,data:calls.append((blueprint,data)) or {'ok':True,'object':{'id':8}})
    assert env['duplicate_actor'](7)['ok']
    assert len(calls)==1 and calls[0][0]=='generated.test'
    assert calls[0][1]['mass']==3 and calls[0][1]['scale']==42
    assert 'stable_id' not in calls[0][1]


def test_duplicate_materials_rebind_only_destination():
    source=SimpleNamespace(id=7,type_id='vehicle.audi.a2')
    target=SimpleNamespace(id=8,type_id=source.type_id)
    material=dict(stable_id='original',blueprint_id=source.type_id,component='VehicleMesh',slot=4,texture='a'*64)
    records={'7':{'stable_id':'original','actor_materials':[material]},
             '8':{'stable_id':'copy','origin':'user'}}
    captured=[];applied=[]
    def prepare(world,document,live,provenance):
        captured.append(document)
        assert live=={'copy':target} and provenance==records
        return SimpleNamespace(apply=lambda:applied.append(True))
    env=functions('copy_duplicate_materials',_provenance=SimpleNamespace(records=lambda _:records),
                  prepare_scene_actor_materials=prepare)
    env['copy_duplicate_materials'](SimpleNamespace(id=1,get_actor=lambda _:target),source,8)
    assert captured[0]['actor_materials']==[{**material,'stable_id':'copy'}]
    assert material['stable_id']=='original' and applied==[True]


@pytest.mark.parametrize('cleanup_failed',[False,True])
def test_material_collision_error_never_retries_successful_spawn(cleanup_failed):
    pose=SimpleNamespace(location=10,rotation=SimpleNamespace(pitch=0,yaw=0,roll=0),
                         get_right_vector=lambda:1,get_forward_vector=lambda:1)
    actor=SimpleNamespace(get_transform=lambda:pose,bounding_box=SimpleNamespace(extent=SimpleNamespace(x=1,y=1)))
    spawned=[];deleted=[]
    def fail(*_):raise RuntimeError('material collision diagnostic')
    def cleanup(actor_id):
        deleted.append(actor_id)
        if cleanup_failed:raise RuntimeError('snapshot timeout')
    env=functions('duplicate_actor',evaluation_active=lambda:False,
        connect_world=lambda:SimpleNamespace(get_actor=lambda _:actor),
        duplicate_spawn_spec=lambda *_:('vehicle.audi.a2',{}),vector=lambda _:dict(x=0,y=0,z=1),
        spawn_object=lambda *_:spawned.append(8) or {'ok':True,'object':{'id':8}},
        copy_duplicate_materials=fail,delete_actor=cleanup)
    with pytest.raises(RuntimeError) as caught:env['duplicate_actor'](7)
    assert 'material collision diagnostic' in str(caught.value)
    if cleanup_failed:
        assert 'actor 8 requires cleanup: snapshot timeout' in str(caught.value)
        assert 'temporary duplicate removed' not in str(caught.value)
    else:assert 'temporary duplicate removed' in str(caught.value)
    assert spawned==[8] and deleted==[8]


@pytest.mark.parametrize('native_collision',[False,True])
def test_duplicate_retries_only_typed_native_collision(native_collision):
    from carla_safety_agent.spawn_errors import SpawnCollision
    pose=SimpleNamespace(location=10,rotation=SimpleNamespace(pitch=0,yaw=0,roll=0),get_right_vector=lambda:1,get_forward_vector=lambda:1)
    actor=SimpleNamespace(get_transform=lambda:pose,bounding_box=SimpleNamespace(extent=SimpleNamespace(x=1,y=1)))
    attempts=[]
    def spawn(*_):
        attempts.append(True)
        if len(attempts)==1:
            if native_collision:raise SpawnCollision('occupied')
            raise RuntimeError('collision during registration; cleanup unconfirmed for actor 8')
        return {'ok':True,'object':{'id':9}}
    env=functions('duplicate_actor',evaluation_active=lambda:False,
        connect_world=lambda:SimpleNamespace(get_actor=lambda _:actor),
        duplicate_spawn_spec=lambda *_:('vehicle.audi.a2',{}),vector=lambda _:dict(x=0,y=0,z=1),spawn_object=spawn)
    if native_collision:
        assert env['duplicate_actor'](7)['object']['id']==9 and len(attempts)==2
    else:
        with pytest.raises(RuntimeError,match='cleanup unconfirmed'):env['duplicate_actor'](7)
        assert len(attempts)==1


def test_duplicate_material_preflight_failure_prevents_creation():
    def fail(*_):raise ValueError('texture checksum mismatch')
    env=functions('duplicate_actor',evaluation_active=lambda:False,
        connect_world=lambda:SimpleNamespace(get_actor=lambda _:object()),
        duplicate_spawn_spec=lambda *_:('vehicle.audi.a2',{}),preflight_duplicate_materials=fail,
        spawn_object=lambda *_:pytest.fail('must not create before material preflight'))
    with pytest.raises(ValueError,match='checksum'):env['duplicate_actor'](7)


@pytest.mark.parametrize('failure',['missing','invalid_image'])
def test_duplicate_source_texture_must_be_readable_image(failure):
    material=dict(stable_id='source',blueprint_id='vehicle.audi.a2',component='VehicleMesh',slot=4,texture='a'*64)
    def texture(_):
        if failure=='missing':raise FileNotFoundError('missing source texture')
        return b'not an image'
    env=functions('preflight_duplicate_materials',
        _provenance=SimpleNamespace(records=lambda _:{'7':{'stable_id':'source','actor_materials':[material]}}),
        MATERIALS=SimpleNamespace(texture=texture))
    with pytest.raises(OSError):
        env['preflight_duplicate_materials'](SimpleNamespace(id=1),SimpleNamespace(id=7,type_id='vehicle.audi.a2'))


def test_focus_never_draws_native_debug_shapes_into_sensor_images():
    tree = ast.parse((Path(__file__).resolve().parents[1]/'tools/livery_bridge.py').read_text())
    names = {'focus_actor', 'focus_static', 'focus_environment'}
    selected = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    assert len(selected) == 3
    for function in selected:
        assert not any(isinstance(n, ast.Attribute) and
                       (n.attr == 'debug' or n.attr.startswith('draw_'))
                       for n in ast.walk(function)), function.name


def test_task_start_does_not_queue_behind_long_asset_operation():
    import threading
    from functools import wraps
    lock=threading.RLock();held=threading.Event();release=threading.Event()
    def owner():
        with lock:held.set();release.wait(5)
    thread=threading.Thread(target=owner);thread.start();assert held.wait(2)
    try:
        env=functions('simulation_operation',wraps=wraps,_simulation_lock=lock)
        def start_e2e():pytest.fail('Queued task unexpectedly executed')
        with pytest.raises(ValueError,match='still running'):env['simulation_operation'](start_e2e)()
    finally:release.set();thread.join(2)


def test_native_asset_registration_blocks_model_start_before_other_access():
    def busy():raise ValueError('native import active')
    env=functions('start_e2e',SESSION=SimpleNamespace(existing_batch_request=lambda _:None),require_asset_import_idle=busy)
    with pytest.raises(ValueError,match='native import active'):env['start_e2e']({'action':'run'})


@pytest.mark.parametrize('payload', [None, [], {}, {'run_id':'capture-a'},
    {'run_id':'capture-a','keep':True,'reason':'keep','expected_revision':0,'path':'/outside'}])
def test_retention_endpoint_rejects_unknown_or_missing_fields(payload):
    def forbidden(*args, **kwargs): pytest.fail('Invalid request changed retention')
    env = functions('set_capture_retention', RETENTION=SimpleNamespace(set_keep=forbidden))
    with pytest.raises(ValueError): env['set_capture_retention'](payload)


def test_retention_endpoint_preserves_explicit_revision_and_flag():
    calls = []
    def record(*args, **kwargs):
        calls.append((args, kwargs))
        return {'revision':3,'records':{}}
    env = functions('set_capture_retention', RETENTION=SimpleNamespace(set_keep=record))
    result = env['set_capture_retention']({'run_id':'capture-a','keep':False,'reason':'release','expected_revision':2})
    assert result['ok'] and result['revision'] == 3
    assert calls == [(('capture-a',False,'release'), {'expected_revision':2})]


@pytest.mark.parametrize('model,directory', [('thinktwice','ThinkTwice'), ('driveadapter','DriveAdapter')])
@pytest.mark.parametrize('empty', [False, True])
def test_original_dependency_failure_precedes_execution_and_material_mutation(tmp_path, monkeypatch, model, directory, empty):
    monkeypatch.setenv('CSA_EXPERIMENTAL_' + model.upper(), '1')
    for relative in ('tools/run_opendrive_native.py', f'integration/opendrive/{model}_agent.py'):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('fixture')
    checkpoint = tmp_path / '.runtime/external-models' / directory / f'{model}-189k.pth'
    if empty:
        checkpoint.parent.mkdir(parents=True)
        checkpoint.write_bytes(b'')
    def forbidden(*args, **kwargs):
        pytest.fail('Missing dependency reached an execution or scene mutation')
    class ForbiddenLock:
        def __enter__(self): forbidden()
        def __exit__(self, *args): pass
    env = functions('start_e2e',
        SESSION=SimpleNamespace(existing_batch_request=lambda _:None, begin=forbidden),
        require_asset_import_idle=lambda:None, UNIAD_PYTHON=SimpleNamespace(is_file=lambda:True),
        evaluation_active=lambda:False, shutil=SimpleNamespace(disk_usage=lambda _:SimpleNamespace(free=8*1024**3)),
        PROJECT_ROOT=tmp_path, connect_world=lambda:object(), require_idle_native_world=lambda _:None,
        algorithm_catalog=lambda *args:[], BENCH2DRIVE_ZOO=tmp_path, BENCH2DRIVE_TCP_ZOO=tmp_path,
        _e2e_lock=ForbiddenLock(), prepare_scene_materials=forbidden,
        subprocess=SimpleNamespace(Popen=forbidden))
    with pytest.raises(RuntimeError, match='Missing or empty experimental checkpoint'):
        env['start_e2e']({'action':'run', 'algorithm':model, 'unified_capture':True})


def test_corrupt_origin_store_refuses_editor_spawn_before_native_mutation():
    def fail(_): raise ValueError('Corrupt provenance')
    env=functions('_spawn_editor_object',connect_world=lambda:SimpleNamespace(id=1),
        _provenance=SimpleNamespace(records=fail))
    with pytest.raises(ValueError,match='Corrupt provenance'):
        env['_spawn_editor_object']('vehicle.test',{})


def test_bundle_diagnostic_validates_request_and_archive_before_native_access():
    def forbidden():pytest.fail('Invalid package reached CARLA')
    def invalid(_):raise ValueError('Invalid package')
    env=functions('diagnose_bundle',connect_world=forbidden,
        BUNDLES=SimpleNamespace(inspect=invalid))
    for payload in ({},{'bundle_id':'x','path':'/tmp'}, {'bundle_id':'x'}):
        with pytest.raises(ValueError):env['diagnose_bundle'](payload)


@pytest.mark.parametrize('name,args', [
    ('apply_livery',(b'',None)), ('apply_livery',(b'',True)),
    ('apply_pedestrian_texture',(b'',None)), ('apply_pedestrian_texture',(b'',-1)),
    ('apply_road_texture',(b'','all')), ('apply_road_texture',(b'','')),
    ('apply_building_texture',(b'','')), ('apply_building_texture',(b'','BP_House160')),
])
def test_implicit_texture_target_rejected_before_world_access(name,args):
    def forbidden(*args,**kwargs): pytest.fail('Implicit target reached native access')
    env=functions(name,decode_texture=forbidden,connect_world=forbidden,evaluation_active=forbidden)
    with pytest.raises(ValueError): env[name](*args)


def test_missing_selected_pedestrian_never_falls_back_to_another():
    world=SimpleNamespace(get_actor=lambda actor_id:None)
    env=functions('apply_pedestrian_texture',decode_texture=lambda *args:(None,None),connect_world=lambda:world)
    with pytest.raises(RuntimeError,match='Select a running pedestrian'):
        env['apply_pedestrian_texture'](b'',42)


@pytest.mark.parametrize('origin',['user','unknown'])
def test_pedestrian_versions_only_for_managed_matching_identity(origin):
    calls=[]
    actor=SimpleNamespace(id=42,type_id='walker.pedestrian.0001')
    world=SimpleNamespace(id=10,get_actor=lambda _:actor,
        apply_color_texture_to_object=lambda *args:calls.append('legacy'))
    def versioned(*args):
        calls.append('versioned');return {'versionable':True}
    env=functions('apply_pedestrian_texture',decode_texture=lambda *args:(SimpleNamespace(width=1024,height=1024),'texture'),
        connect_world=lambda:world,_provenance=SimpleNamespace(records=lambda _:{'42':{'origin':origin,'type_id':actor.type_id}}),
        apply_versioned_livery=versioned,runtime_name_for_actor=lambda *_:'ExactWalker',
        carla=SimpleNamespace(MaterialParameter=SimpleNamespace(Diffuse=0)))
    result=env['apply_pedestrian_texture'](b'',42)
    assert calls==['versioned' if origin=='user' else 'legacy']
    assert result.get('versionable',False)==(origin=='user')


@pytest.mark.parametrize('scope,confirmed,expected', [
    ('Road_Road_1',False,['Road_Road_1']), ('all',True,['Road_Road_1','Road_Road_2'])])
def test_road_texture_scope_is_explicit(scope,confirmed,expected):
    calls=[]
    world=SimpleNamespace(get_names_of_all_objects=lambda:['Road_Road_2','BP_House16','Road_Road_1'],
        apply_color_texture_to_objects=lambda names,*args:calls.append(names))
    env=functions('apply_road_texture',decode_texture=lambda *args:(SimpleNamespace(width=1,height=1),'texture'),
        connect_world=lambda:world,carla=SimpleNamespace(MaterialParameter=SimpleNamespace(Diffuse=0)))
    env['apply_road_texture'](b'',scope,confirmed_all=confirmed)
    assert calls==[expected]


def test_generated_mesh_uniform_scale_sets_axis_overrides():
    attributes = {}
    blueprint = SimpleNamespace(set_attribute=lambda key,value:attributes.update({key:value}),
                                has_attribute=lambda key:True)
    world = SimpleNamespace(id=1,get_blueprint_library=lambda:SimpleNamespace(find=lambda _:blueprint))
    def stop_before_spawn(**kwargs): raise RuntimeError('parameters observed')
    env = functions('_spawn_editor_object', connect_world=lambda:world,
        _provenance=SimpleNamespace(records=lambda _:{}),
        BLENDER=SimpleNamespace(registry=lambda:{'generated.prop.test':{'mesh_path':'/Game/Test','default_scale':100}}),
        carla=SimpleNamespace(Location=stop_before_spawn))
    with pytest.raises(RuntimeError,match='parameters observed'):
        env['_spawn_editor_object']('generated.prop.test',{})
    assert all(attributes[key]=='100.0' for key in ('scale','scale_x','scale_y','scale_z'))


def test_invalid_actor_update_does_not_query_or_mutate_world():
    def forbidden(*args,**kwargs):
        pytest.fail('Invalid transform must be rejected before native or worker access')
    env=functions('update_actor', evaluation_active=forbidden,connect_world=forbidden,
                  evaluation_command=forbidden)
    with pytest.raises(ValueError):
        env['update_actor'](0,{'location':{'x':float('nan')}})


def test_repeated_batch_start_returns_before_native_access():
    def forbidden(*args, **kwargs):
        pytest.fail('Repeated dispatch must not touch simulation')
    existing = {'run_id': 'original', 'state': 'completed', 'kind': 'rule-run'}
    env = functions('start_e2e', SESSION=SimpleNamespace(existing_batch_request=lambda _: existing),
                    evaluation_active=forbidden, connect_world=forbidden)
    result = env['start_e2e']({'action': 'rule-run', 'batch_attempt_id': 'a', 'batch_job_id': 'j'})
    assert result['replayed'] is True and result['execution_id'] == 'original'


@pytest.mark.parametrize('value', ['0','bad','nan','1.5'])
def test_sensor_capture_invalid_quota_rejected_before_native_access(monkeypatch,value):
    monkeypatch.setenv('CSA_CAPTURE_QUOTA_GIB',value)
    def forbidden(*args,**kwargs):
        pytest.fail('Invalid recording configuration must not access simulator or execution state')
    env=functions('start_e2e',SESSION=SimpleNamespace(existing_batch_request=lambda _:None),
        require_asset_import_idle=lambda:None,evaluation_active=forbidden,connect_world=forbidden)
    with pytest.raises(ValueError,match='CSA_CAPTURE_QUOTA_GIB'):
        env['start_e2e']({'action':'sensor-rig','recording':True})


def test_nonrecording_sensor_session_does_not_require_valid_quota(monkeypatch):
    monkeypatch.setenv('CSA_CAPTURE_QUOTA_GIB','bad')
    def reached():
        raise RuntimeError('passed recording precheck')
    env=functions('start_e2e',SESSION=SimpleNamespace(existing_batch_request=lambda _:None),
        require_asset_import_idle=lambda:None,evaluation_active=reached)
    with pytest.raises(RuntimeError,match='passed recording precheck'):
        env['start_e2e']({'action':'sensor-rig','recording':False})


@pytest.mark.parametrize('action',['run','rule-run'])
@pytest.mark.parametrize('recording',[True,False])
def test_model_and_rule_recording_quota_gate_precedes_launch(monkeypatch,action,recording):
    monkeypatch.setenv('CSA_CAPTURE_QUOTA_GIB','invalid')
    def reached():
        raise RuntimeError('passed quota gate')
    env=functions('start_e2e',SESSION=SimpleNamespace(existing_batch_request=lambda _:None),
        require_asset_import_idle=lambda:None,UNIAD_PYTHON=SimpleNamespace(is_file=lambda:True),
        evaluation_active=reached)
    if recording:
        with pytest.raises(ValueError,match='CSA_CAPTURE_QUOTA_GIB'):
            env['start_e2e']({'action':action,'unified_capture':True})
    else:
        with pytest.raises(RuntimeError,match='passed quota gate'):
            env['start_e2e']({'action':action,'unified_capture':False})


@pytest.mark.parametrize('state', ['empty', 'generating', 'needs_attention', 'exported', 'corrupt'])
@pytest.mark.parametrize('kind', ['generation', 'import'])
def test_asset_restart_status_real_http_read_only(tmp_path, state, kind):
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from urllib.parse import urlparse, parse_qs
    from urllib.request import urlopen
    from urllib.error import HTTPError
    from carla_safety_agent.blender_pipeline import BlenderPipeline
    from carla_safety_agent.restart_guard import verify_asset_jobs_idle
    pipeline = BlenderPipeline(tmp_path)
    if kind == 'import':
        state = {'generating': 'importing', 'exported': 'registered'}.get(state, state)
    attempt_id = 'a' * 32 if kind == 'import' else 'abc123'
    journal = pipeline.runtime / 'abc123' / (
        f'import-attempt-{attempt_id}.json' if kind == 'import' else 'generation.json')
    if state != 'empty':
        journal.parent.mkdir(parents=True)
        journal.write_text('{}' if state == 'corrupt' else json.dumps({
            'schema_version': f'carla-asset-{kind}/1', 'job_id': 'abc123',
            'attempt_id': attempt_id, 'started_at': 1, 'state': state,
            'report_path': str(journal)}))
    before = journal.read_bytes() if journal.exists() else None
    source = Path(__file__).resolve().parents[1] / 'tools/livery_bridge.py'
    node = next(n for n in ast.parse(source.read_text()).body
                if isinstance(n, ast.ClassDef) and n.name == 'Handler')
    env = dict(BaseHTTPRequestHandler=BaseHTTPRequestHandler, urlparse=urlparse,
               parse_qs=parse_qs, json=json, BLENDER=pipeline,
               FRONTEND_ORIGIN='http://localhost:3000')
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), 'exec'), env)
    server = ThreadingHTTPServer(('127.0.0.1', 0), env['Handler'])
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f'http://127.0.0.1:{server.server_port}/blender/restart-status'
        if state == 'corrupt':
            with pytest.raises(HTTPError) as caught:
                urlopen(url, timeout=5)
            with caught.value as response:
                assert response.code == 400
                payload = json.load(response)
            assert payload['ok'] is False
            with pytest.raises(ValueError, match='unknown'):
                verify_asset_jobs_idle(payload)
        else:
            with urlopen(url, timeout=5) as response:
                assert response.status == 200
                payload = json.load(response)
            assert payload['ok'] is True
            if state in ('generating', 'importing', 'needs_attention'):
                assert payload['unresolved'][0]['state'] == state
                with pytest.raises(ValueError, match='unresolved'):
                    verify_asset_jobs_idle(payload)
            else:
                verify_asset_jobs_idle(payload)
        assert (journal.read_bytes() if journal.exists() else None) == before
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_invalid_quota_over_real_http_never_touches_simulator(monkeypatch):
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from urllib.parse import urlparse, parse_qs
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError
    monkeypatch.setenv('CSA_CAPTURE_QUOTA_GIB','invalid')
    calls=[]
    def forbidden():
        calls.append('native')
        raise RuntimeError('Unexpected simulator access')
    env=functions('start_e2e',SESSION=SimpleNamespace(existing_batch_request=lambda _:None),
        require_asset_import_idle=lambda:None,evaluation_active=forbidden,connect_world=forbidden)
    env.update(BaseHTTPRequestHandler=BaseHTTPRequestHandler,urlparse=urlparse,parse_qs=parse_qs,
               json=json,FRONTEND_ORIGIN='http://localhost:3000')
    source=Path(__file__).resolve().parents[1]/'tools/livery_bridge.py'
    node=next(n for n in ast.parse(source.read_text()).body if isinstance(n,ast.ClassDef) and n.name=='Handler')
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(source),'exec'),env)
    server=ThreadingHTTPServer(('127.0.0.1',0),env['Handler'])
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    try:
        request=Request(f'http://127.0.0.1:{server.server_port}/collection/start',
            data=json.dumps({'recording':True,'mode':'stationary','frames':10}).encode(),
            headers={'Content-Type':'application/json'},method='POST')
        with pytest.raises(HTTPError) as caught:
            urlopen(request,timeout=5)
        error=caught.value
        assert error.code==400
        payload=json.load(error)
        assert payload['ok'] is False and 'CSA_CAPTURE_QUOTA_GIB' in payload['error']
        assert calls==[]
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)


@pytest.mark.parametrize('recording',[True,False])
def test_recording_toggle_invalid_quota_preserves_stop_access(tmp_path,monkeypatch,recording):
    import uuid
    monkeypatch.setenv('CSA_CAPTURE_QUOTA_GIB','bad')
    target=tmp_path/'collection-request.json'
    target.write_text('{"id":"previous"}')
    env=functions('collection_request',_evaluation_control_dir=tmp_path,
        evaluation_active=lambda:True,SESSION=SimpleNamespace(snapshot=lambda:{'run_id':'current'}),
        uuid=uuid,json=json)
    if recording:
        with pytest.raises(ValueError,match='request not written'):
            env['collection_request']({'recording':True})
        assert target.read_text()=='{"id":"previous"}'
    else:
        result=env['collection_request']({'recording':False})
        assert result['request']['recording'] is False
        assert json.loads(target.read_text())['execution_id']=='current'


@pytest.mark.parametrize('payload',[{}, {'run_id':None}, {'run_id':''}, {'run_id':'old'}, {'run_id':'current','extra':True}])
def test_model_stop_rejects_missing_or_stale_identity_without_signalling(payload):
    import threading
    env=functions('stop_model_run',_e2e_lock=threading.RLock(),
        SESSION=SimpleNamespace(snapshot=lambda:{'run_id':'current','kind':'run','state':'running'}),
        stop_e2e=lambda:pytest.fail('Stale stop must not signal'))
    with pytest.raises(ValueError):env['stop_model_run'](payload)


def test_model_stop_does_not_interrupt_recovery_and_preserves_identity():
    import threading
    current={'run_id':'current','kind':'run','state':'running'}
    calls=[]
    env=functions('stop_model_run',_e2e_lock=threading.RLock(),SESSION=SimpleNamespace(snapshot=lambda:current),
        stop_e2e=lambda:calls.append('stop') or {'ok':True,'state':'stopping'})
    assert env['stop_model_run']({'run_id':'current'})['run_id']=='current'
    current['state']='recovering'
    assert env['stop_model_run']({'run_id':'current'})['state']=='recovering'
    assert calls==['stop']
    current['kind']='sensor-rig'
    with pytest.raises(ValueError):env['stop_model_run']({'run_id':'current'})


def test_texture_recovery_uses_durable_desired_even_if_override_write_was_lost():
    before, desired, calls = [], [{'target':'house', 'component':'mesh', 'slot':0,'texture':'a'*64}], []
    recovery = {'episode':7, 'map':'Town04', 'before':before, 'desired':desired}
    world = SimpleNamespace(id=7, get_map=lambda:SimpleNamespace(name='Town04'))
    def prepare(w, document, previous):
        assert w is world and previous == desired
        assert document == {'environment_materials':before}
        return SimpleNamespace(apply=lambda:calls.append('restored'))
    env = functions('restore_execution_textures',
        SESSION=SimpleNamespace(snapshot=lambda:{'configuration':{'texture_recovery':recovery}}),
        prepare_scene_materials=prepare)
    env['restore_execution_textures'](world)
    env['restore_execution_textures'](world)
    assert calls == ['restored', 'restored']
    world.id = 8
    with pytest.raises(RuntimeError, match='world changed'): env['restore_execution_textures'](world)
    assert len(calls) == 2


@pytest.mark.parametrize('failure', ['apply', 'launch', 'recovery', 'attach'])
def test_texture_start_failures_restore_or_retain_recovery_ownership(failure):
    source = Path(__file__).resolve().parents[1]/'tools/livery_bridge.py'
    start = next(n for n in ast.parse(source.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='start_e2e')
    block = next(n for n in ast.walk(start) if isinstance(n,ast.Try)
        and any(isinstance(c,ast.Call) and isinstance(c.func,ast.Attribute) and c.func.attr=='Popen' for s in n.body for c in ast.walk(s)))
    calls = []
    def operation(name, fails=False):
        calls.append(name)
        if fails: raise RuntimeError(name+' failed')
    child = SimpleNamespace(pid=123)
    env = {'launched':None, 'texture_transaction':SimpleNamespace(apply=lambda:operation('apply',failure=='apply')),
        'subprocess':SimpleNamespace(STDOUT=-2, Popen=lambda *a,**kw:operation('launch',failure in ('launch','recovery')) or child),
        'command':[], 'PROJECT_ROOT':Path('/local'), 'env':{},
        'log_stream':SimpleNamespace(close=lambda:operation('close')),
        'SESSION':SimpleNamespace(attach=lambda _:operation('attach',failure=='attach'),
                                  transition=lambda state,**kw:operation(state)),
        '_e2e_job':{}, 'restore_editor_world':lambda:operation('restore',failure=='recovery'),
        '_abort_e2e_start':lambda proc,exc:operation('retain_child'),
        'action':'run', 'data':{}, '_e2e_pid':SimpleNamespace(write_text=lambda _:None)}
    with pytest.raises(RuntimeError): exec(compile(ast.Module(body=[block],type_ignores=[]),str(source),'exec'),env)
    assert calls[0]=='apply' and calls[-1]=='close'
    if failure=='attach':
        assert 'retain_child' in calls and 'restore' not in calls
    else:
        assert calls.index('recovering') < calls.index('restore')
        assert ('failed' in calls) == (failure!='recovery')


def test_texture_recovery_rejects_changed_episode_before_settings_write():
    def forbidden(*args): pytest.fail('Foreign world must not be modified')
    world = SimpleNamespace(id=8, get_settings=forbidden)
    env = functions('restore_editor_world', _carla_client=SimpleNamespace(get_world=lambda:world),
        SESSION=SimpleNamespace(snapshot=lambda:{'configuration':{'texture_recovery':{'episode':7,'map':'Town04'}}}))
    with pytest.raises(RuntimeError,match='world changed'): env['restore_editor_world']()


@pytest.mark.parametrize('invalid', ['target','slot','digest',None])
def test_material_transaction_preflights_all_references_before_writing(invalid):
    from carla_safety_agent.material_library import MaterialTransaction
    calls = []
    records = [{'target':'road','component':'mesh','slot':0,'texture':'a'*64}]
    world = SimpleNamespace(id=7, get_map=lambda:SimpleNamespace(name='Town04'),
        get_names_of_all_objects=lambda:[] if invalid=='target' else ['road'],
        apply_color_texture_to_object=lambda *args:calls.append('rpc'))
    def texture(digest):
        if invalid=='digest': raise ValueError('Texture checksum mismatch')
        return b'image'
    library = SimpleNamespace(overrides=lambda _: {}, texture=texture,
        catalog=lambda _:{'actors':{'road':[{'component':'mesh','slots':[{'slot':0,
            'status':'missing' if invalid=='slot' else 'uv0_ready'}]}]}},
        record=lambda *args:calls.append('record'))
    env = functions('prepare_scene_materials', MATERIALS=library, MaterialTransaction=MaterialTransaction,
        decode_texture=lambda *args:(None,'decoded'), carla=SimpleNamespace(MaterialParameter=SimpleNamespace(Diffuse='diffuse')))
    if invalid:
        with pytest.raises(ValueError): env['prepare_scene_materials'](world,{'environment_materials':records})
        assert calls==[]
    else:
        tx=env['prepare_scene_materials'](world,{'environment_materials':records})
        assert calls==[]
        tx.apply()
        assert calls==['rpc','record']


def test_weather_restore_rejects_stale_execution_before_rpc():
    def forbidden(*args): pytest.fail('Stale weather restore touched world')
    env = functions('restore_execution_weather', SESSION=SimpleNamespace(snapshot=lambda: {'run_id': 'new', 'state': 'completed'}),
                    evaluation_active=forbidden, connect_world=forbidden)
    with pytest.raises(ValueError): env['restore_execution_weather']({'run_id': 'old', 'source_run_id': 'source'})


def test_weather_restore_uses_saved_values():
    writes = []; weather = SimpleNamespace(precipitation=75.)
    world = SimpleNamespace(get_settings=lambda: SimpleNamespace(synchronous_mode=False),
        get_map=lambda: SimpleNamespace(name='Town04'), get_weather=lambda: weather,
        set_weather=lambda w: writes.append(w.precipitation))
    journal = SimpleNamespace(snapshot=lambda: {'run_id': 'current', 'state': 'completed'},
        read_execution=lambda _: {'configuration': {'starting_scene': {'map': 'Town04', 'weather': {'precipitation': 0.}}}})
    env = functions('restore_execution_weather', SESSION=journal, evaluation_active=lambda: False, connect_world=lambda: world)
    assert env['restore_execution_weather']({'run_id': 'current', 'source_run_id': 'source'})['weather_restored']
    assert writes == [0.]


def test_texture_identity_rejects_same_model_ambiguity():
    env = functions('runtime_name_for_actor', _actor_object_names={},_provenance=SimpleNamespace(records=lambda _:{}))
    world = SimpleNamespace(id=10,get_names_of_all_objects=lambda:['BP_TeslaM3_C_1','BP_TeslaM3_C_2'])
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


def test_material_restore_journals_previous_texture_before_native_call(tmp_path):
    from carla_safety_agent.material_history import MaterialHistory
    store=MaterialHistory(tmp_path/'history');calls=[]
    def native(*args):
        pending=store.read(next(store.root.glob('*.json')).stem)
        assert pending['before']=='a'*64 and pending['after'] is None and pending['state']=='attempting'
        calls.append(args)
    env=functions('apply_material_slot',MATERIAL_HISTORY=store,
        material_catalog=lambda _:dict(target='house',components=[dict(component='mesh',slots=[dict(slot=2,status='uv0_ready')])],overrides=[dict(component='mesh',slot=2,texture='a'*64)]),
        connect_world=lambda:SimpleNamespace(id=7,apply_color_texture_to_object=native),
        carla=SimpleNamespace(TextureColor=lambda *_:'empty',MaterialParameter=SimpleNamespace(Diffuse='diffuse')),
        MATERIALS=SimpleNamespace(record=lambda *args:calls.append(args)))
    result=env['apply_material_slot'](dict(object_id=123,component='mesh',slot=2))
    assert store.read(result['material_operation_id'])['state']=='confirmed' and len(calls)==2


def test_material_recovery_bridge_preserves_failure_and_applies_exact_slot(tmp_path):
    from carla_safety_agent.material_history import MaterialHistory
    store=MaterialHistory(tmp_path/'history')
    identity=dict(episode='7',object_id='123',target='house',component='mesh',slot=2)
    def fail():raise RuntimeError('original native uncertainty')
    with pytest.raises(RuntimeError):store.execute(identity,None,'a'*64,fail)
    op=next(store.root.glob('*.json')).stem
    inspection=store.inspect(op,lambda _:None);calls=[]
    world=SimpleNamespace(id=7,get_settings=lambda:SimpleNamespace(synchronous_mode=False),
        get_actors=lambda:SimpleNamespace(filter=lambda _:[]),
        apply_color_texture_to_object=lambda *args:calls.append(args))
    env=functions('recover_material_history','material_history_callbacks',
        MATERIAL_HISTORY=store,evaluation_active=lambda:False,connect_world=lambda:world,
        material_catalog=lambda _:dict(target='house',components=[dict(component='mesh',slots=[dict(slot=2,status='uv0_ready')])],overrides=[]),
        carla=SimpleNamespace(TextureColor=lambda *_:'empty',MaterialParameter=SimpleNamespace(Diffuse='diffuse')),
        MATERIALS=SimpleNamespace(record=lambda *args:calls.append(args),texture=lambda _:b'valid-texture'),
        decode_texture=lambda *_:('image','decoded'))
    payload=dict(operation_id=op,inspection_token=inspection['inspection_token'],choice='target',registered_texture=None,confirmed=True)
    with pytest.raises(ValueError):env['recover_material_history']({**payload,'registered_texture':'b'*64})
    assert calls==[]
    result=env['recover_material_history'](payload)
    assert result['recovery']['state']=='confirmed' and result['original_state']=='needs_attention'
    assert calls==[('house|csa|mesh|2|apply','diffuse','decoded'),(7,'house','mesh',2,'a'*64)]
    with pytest.raises(ValueError):env['recover_material_history'](payload)
    assert len(calls)==2


@pytest.mark.parametrize('path,expected', [('/', 200), ('/?probe=1', 200),
    ('/nonexistent', 404), ('/blender/restart-status-typo', 404), ('/datasets/typo', 404)])
def test_get_unknown_endpoint_is_not_service_health(path, expected):
    import io
    from urllib.parse import urlparse, parse_qs
    source = Path(__file__).resolve().parents[1] / 'tools/livery_bridge.py'
    node = next(n for n in ast.parse(source.read_text()).body
                if isinstance(n, ast.ClassDef) and n.name == 'Handler')
    env = dict(BaseHTTPRequestHandler=object, urlparse=urlparse, parse_qs=parse_qs, json=json)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), 'exec'), env)
    handler = env['Handler']()
    statuses = []
    handler._headers = lambda status=200: statuses.append(status)
    handler.path, handler.wfile = path, io.BytesIO()
    handler.do_GET()
    assert statuses == [expected]
    payload = json.loads(handler.wfile.getvalue())
    assert payload['ok'] is (expected == 200)
    if expected == 404:
        assert payload['code'] == 'unknown_endpoint'
        assert 'service' not in payload


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


@pytest.mark.parametrize('query,expected', [('job_id=abc',200), ('',400),
    ('job_id=',400), ('job_id=abc&job_id=other',400), ('job_id=abc&job_id=',400),
    ('job_id=abc&extra=',400), ('job_id=missing',400), ('job_id=..%2Foutside',400)])
def test_reopen_export_http_route(query, expected):
    import io
    from urllib.parse import urlparse, parse_qs
    source = Path(__file__).resolve().parents[1] / 'tools/livery_bridge.py'
    node = next(n for n in ast.parse(source.read_text()).body
                if isinstance(n, ast.ClassDef) and n.name == 'Handler')
    calls=[]
    def exported(job):
        calls.append(job)
        if job != 'abc':
            raise ValueError('No confirmed export')
        return {'ok':True,'job_id':job,'reopened':True}
    env={'BaseHTTPRequestHandler':object,'urlparse':urlparse,'parse_qs':parse_qs,
         'json':json,'BLENDER':SimpleNamespace(exported_asset=exported)}
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(source),'exec'),env)
    handler=env['Handler']()
    statuses=[]
    handler._headers=lambda status=200:statuses.append(status)
    handler.path='/blender/exported?'+query
    handler.wfile=io.BytesIO()
    handler.do_GET()
    assert statuses==[expected]
    payload=json.loads(handler.wfile.getvalue())
    assert payload['ok'] is (expected==200)
    if expected==200:
        assert payload['reopened'] and payload['job_id']=='abc'
    if query in ('','job_id=abc&job_id=other','job_id=abc&job_id=','job_id=abc&extra='):
        assert calls==[]


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


@pytest.mark.parametrize('name', ['connect_world', 'restore_editor_world'])
def test_missing_simulator_never_enters_native_client(name):
    import threading
    def unavailable(host, port):
        raise RuntimeError('transport unavailable')
    def forbidden(*args):
        pytest.fail('Native CARLA call would block offline HTTP requests')
    env = functions(name, evaluation_active=lambda: False,
        _simulation_lock=threading.RLock(), _world_episode=None,
        require_simulator_connection=unavailable,
        _carla_client=SimpleNamespace(get_world=forbidden),
        carla=SimpleNamespace(Client=forbidden))
    with pytest.raises(RuntimeError, match='transport unavailable'):
        env[name]()


def test_first_connection_cannot_infer_dynamic_actor_history(tmp_path):
    import threading
    from carla_safety_agent.provenance import ActorProvenance
    store = ActorProvenance(tmp_path/'actors.json')
    known = SimpleNamespace(id=1, type_id='vehicle.test')
    unobserved = SimpleNamespace(id=2, type_id='vehicle.test')
    store.mark(10, [known], 'user')
    world = SimpleNamespace(id=10, get_actors=lambda: [known, unobserved])
    env = functions('connect_world', evaluation_active=lambda:False,
        _simulation_lock=threading.RLock(), _world_episode=None,
        _carla_client=SimpleNamespace(get_world=lambda:world), _provenance=store,
        _editor_actors=set(), _environment_cache={}, _actor_object_names={})
    assert env['connect_world']() is world
    assert store.origin(10, known) == 'user'
    assert store.origin(10, unobserved) == 'unknown'
    assert env['_world_episode'] == 10


def test_failed_provenance_initialization_is_not_cached():
    import threading
    def fail(*args, **kwargs): raise OSError('disk unavailable')
    world = SimpleNamespace(id=10, get_actors=lambda:[])
    env = functions('connect_world', evaluation_active=lambda:False,
        _simulation_lock=threading.RLock(), _world_episode=None,
        _carla_client=SimpleNamespace(get_world=lambda:world),
        _provenance=SimpleNamespace(mark=fail), _editor_actors=set(),
        _environment_cache={}, _actor_object_names={})
    for _ in range(2):
        with pytest.raises(OSError): env['connect_world']()
        assert env['_world_episode'] is None


def test_stop_does_not_interrupt_cleanup_twice():
    import threading
    env = functions('stop_e2e', _e2e_lock=threading.Lock(), _e2e_job={'state': 'stopping'})
    assert env['stop_e2e']() == {'ok': True, 'state': 'stopping'}


@pytest.mark.parametrize('state,code,expected', [('running', 0, 'succeeded'),
                                              ('stopping', 130, 'stopped'),
                                              ('stopping', 0, 'stopped'),
                                              ('stopping', 1, 'failed')])
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


@pytest.mark.parametrize('state,code', [('running', 0), ('stopping', 130)])
def test_world_recovery_failure_never_reports_execution_success(tmp_path, state, code):
    import threading
    import time
    process = SimpleNamespace(pid=123, wait=lambda: code)
    pid = tmp_path/'pid'
    pid.write_text('123')
    job = {'state': state, 'kind': 'preset-run', 'results': None}
    transitions = []
    def restore():
        raise RuntimeError('CARLA RPC unavailable')
    env = functions('_finish_e2e', _e2e_pid=pid, _e2e_process=process,
                    _e2e_lock=threading.Lock(), _e2e_job=job, Path=Path, time=time,
                    restore_editor_world=restore,
                    SESSION=SimpleNamespace(transition=lambda *args, **kwargs: transitions.append((args, kwargs))))
    env['_finish_e2e'](process)
    assert job['state'] == 'failed'
    assert job['cleanup_error'] == 'CARLA RPC unavailable'
    args, result = transitions[-1]
    assert args == ('recovering',)
    assert result['outcome']['execution'] == 'failed'
    assert result['outcome']['failure_category'] == 'world_recovery'
    assert not pid.exists()


def test_material_mutation_entrypoints_keep_simulation_guard():
    path = Path(__file__).resolve().parents[1]/'tools/livery_bridge.py'
    tree = ast.parse(path.read_text())
    required = {'apply_material_slot', 'material_history_action', 'recover_material_history',
                'actor_material_history_action', 'recover_actor_material_history'}
    nodes = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    for name in required:
        assert any(isinstance(d, ast.Name) and d.id == 'simulation_operation'
                   for d in nodes[name].decorator_list), name


def test_material_history_rejects_changed_registry_before_native_write():
    from types import SimpleNamespace
    calls = []
    world = SimpleNamespace(id=1, apply_color_texture_to_object=lambda *args: calls.append(args))
    info = {'target': 'house', 'components': [{'component': 'mesh', 'slots': [
        {'slot': 0, 'status': 'uv0_ready'}]}],
        'overrides': [{'component': 'mesh', 'slot': 0, 'texture': 'c'*64}]}
    env = functions('material_history_callbacks', material_catalog=lambda _: info)
    verify, _ = env['material_history_callbacks'](world)
    identity = dict(episode='1', object_id='2', target='house', component='mesh', slot=0)
    with pytest.raises(ValueError, match='changed outside this history'):
        verify(identity, 'b'*64, 'a'*64)
    assert calls == []


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


@pytest.mark.parametrize('payload', [None, [], {}, {'_checkpoint': None},
    {'_checkpoint': {}}, {'_checkpoint': {'records': [None], 'global_record': {'status': 'Completed'}}},
    {'_checkpoint': {'records': [{'status': 'Completed'}], 'global_record': None}}])
def test_malformed_benchmark_result_is_failure_not_watcher_exception(tmp_path, payload):
    result = tmp_path / 'result.json'
    result.write_text(json.dumps(payload))
    env = functions('_benchmark_result_failed', Path=Path, json=json)
    assert env['_benchmark_result_failed'](result)


def test_invalid_utf8_result_is_failure(tmp_path):
    result = tmp_path / 'result.json'
    result.write_bytes(b'\xff')
    env = functions('_benchmark_result_failed', Path=Path, json=json)
    assert env['_benchmark_result_failed'](result)


@pytest.mark.parametrize('nested', [True, False])
@pytest.mark.parametrize('driving_status', ['passed', 'failed'])
def test_native_valid_driving_outcome_is_not_execution_failure(tmp_path, nested, driving_status):
    metrics = dict(scenario_id='test', status=driving_status, collision=False,
                   min_ttc_s=None, min_distance_m=10., elapsed_s=4., risk_score=0., failure_reasons=[])
    payload = {'scenario': {'scenario_id': 'test'}}
    if nested:
        payload.update(schema_version='carla-safety-evaluation/0.1', result=metrics)
    else:
        payload.update(metrics)
    path = tmp_path / 'result.json'
    env = functions('_benchmark_result_failed', Path=Path, json=json)
    path.write_text(json.dumps(payload))
    assert not env['_benchmark_result_failed'](path)
    for key, value in [('elapsed_s', float('nan')), ('collision', 'false'),
                       ('scenario_id', 'other'), ('failure_reasons', None)]:
        broken = json.loads(json.dumps(payload))
        (broken['result'] if nested else broken)[key] = value
        path.write_text(json.dumps(broken))
        assert env['_benchmark_result_failed'](path)


def test_unrelated_nonempty_json_is_not_native_result(tmp_path):
    path = tmp_path / 'result.json'
    path.write_text('{"hello": "world"}')
    env = functions('_benchmark_result_failed', Path=Path, json=json)
    assert env['_benchmark_result_failed'](path)


@pytest.mark.parametrize('execution,scenario,expected', [
    ('owned', 'hash', False), ('old-run', 'hash', True), ('owned', 'old-hash', True),
    (None, 'hash', True), ('owned', None, True)])
def test_native_result_must_match_requested_execution_and_scenario(tmp_path, execution, scenario, expected):
    import hashlib
    digest = hashlib.sha256(b'{"scenario_id":"s"}').hexdigest()
    scenario = digest if scenario == 'hash' else scenario
    path = tmp_path / 'result.json'
    path.write_text(json.dumps(dict(execution_id=execution, scenario_sha256=scenario,
        scenario={'scenario_id': 's'}, scenario_id='s', status='passed', collision=False,
        failure_reasons=[], min_ttc_s=None, min_distance_m=1., elapsed_s=4., risk_score=0.)))
    env = functions('_benchmark_result_failed', Path=Path, json=json)
    assert env['_benchmark_result_failed'](path, 'owned', digest) is expected


@pytest.mark.parametrize('changed', [{'scenario_id': 's', 'seed': 99},
                                     {'scenario_id': 's', 'seed': float('nan')}, None])
def test_correct_hash_label_cannot_hide_modified_scenario(tmp_path, changed):
    import hashlib
    digest = hashlib.sha256(b'{"scenario_id":"s"}').hexdigest()
    path = tmp_path / 'result.json'
    path.write_text(json.dumps(dict(execution_id='owned', scenario_sha256=digest,
        scenario=changed, scenario_id='s', status='passed', collision=False,
        failure_reasons=[], min_ttc_s=None, min_distance_m=1., elapsed_s=4., risk_score=0.)))
    env = functions('_benchmark_result_failed', Path=Path, json=json)
    assert env['_benchmark_result_failed'](path, 'owned', digest)


@pytest.mark.parametrize('contents', ['{}', 'null', '{"_checkpoint": null}', '{'])
def test_corrupt_result_finishes_session_as_benchmark_failure(tmp_path, contents):
    import threading
    import time
    result = tmp_path / 'result.json'
    result.write_text(contents)
    calls = []
    process = SimpleNamespace(pid=123, wait=lambda: 0)
    job = {'kind': 'run', 'state': 'running', 'results': str(result)}
    env = functions('_benchmark_result_failed', '_finish_e2e', Path=Path, json=json, time=time,
        _e2e_process=process, _e2e_job=job, _e2e_pid=tmp_path/'pid',
        _e2e_lock=threading.RLock(), restore_editor_world=lambda: None,
        SESSION=SimpleNamespace(transition=lambda state, **kw: calls.append((state, kw))))
    env['_finish_e2e'](process)
    assert calls[-1][0] == 'failed'
    assert calls[-1][1]['outcome']['failure_category'] == 'benchmark_result'
    assert calls[-1][1]['outcome']['benchmark_failed'] is True
    assert job['state'] == 'failed'


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
    env = functions('restore_scene', connect_world=lambda:world, live_scene_bindings=lambda *_:{},
        SCENES=SimpleNamespace(read=lambda *args:{'document':document}), validate_scene=validate_scene,
        BLENDER=SimpleNamespace(registry=lambda:{}), _provenance=SimpleNamespace(records=lambda _:{}),
        prepare_scene_materials=lambda *args:None, prepare_scene_visibility=lambda *args:None,
        spawn_object=lambda *args:calls.append('spawn'), update_actor=lambda *args:calls.append('move'))
    with pytest.raises(ValueError, match='Unsupported weather'):
        env['restore_scene']({'scene_id':'test'})
    assert calls == []


@pytest.mark.parametrize('fail_after_weather', [False, True])
def test_scene_restore_weather_round_trip_and_transaction_rollback(fail_after_weather):
    from carla_safety_agent.scene_store import validate_scene
    keys = ('cloudiness', 'precipitation', 'precipitation_deposits', 'wind_intensity',
            'sun_azimuth_angle', 'sun_altitude_angle', 'fog_density', 'fog_distance',
            'fog_falloff', 'wetness', 'scattering_intensity', 'mie_scattering_scale',
            'rayleigh_scattering_scale', 'dust_storm')
    original = {key: float(i) / 10 for i, key in enumerate(keys)}
    desired = {key: value + 1 for key, value in original.items()}
    state = {'weather': dict(original)}
    calls = []

    def set_weather(weather):
        state['weather'] = dict(vars(weather))
        calls.append(dict(state['weather']))

    def apply_visibility():
        if fail_after_weather:
            raise RuntimeError('visibility failure')

    spectator = SimpleNamespace(get_transform=lambda:'original-view',
        set_transform=lambda value:calls.append(value))
    world = SimpleNamespace(id=1, get_map=lambda:SimpleNamespace(name='Town04'),
        get_weather=lambda:SimpleNamespace(**state['weather']), set_weather=set_weather,
        get_spectator=lambda:spectator)
    document = {'map':'Town04', 'objects':[], 'weather':desired}
    env = functions('restore_scene', connect_world=lambda:world, live_scene_bindings=lambda *_:{},
        SCENES=SimpleNamespace(read=lambda *args:{'document':document}), validate_scene=validate_scene,
        BLENDER=SimpleNamespace(registry=lambda:{}), _provenance=SimpleNamespace(records=lambda _:{}),
        prepare_scene_materials=lambda *args:None,
        prepare_scene_visibility=lambda *args:SimpleNamespace(apply=apply_visibility,
            rollback=lambda:calls.append('visibility-rollback')))
    if fail_after_weather:
        with pytest.raises(RuntimeError, match='visibility failure'):
            env['restore_scene']({'scene_id':'test'})
        assert state['weather'] == original
        assert calls == [desired, 'visibility-rollback', original, 'original-view']
    else:
        assert env['restore_scene']({'scene_id':'test'})['ok']
        assert state['weather'] == desired
        assert calls == [desired]


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


def test_rule_stop_identity_and_terminal_idempotence():
    import threading
    current = {'kind':'rule-run','run_id':'new','state':'running'}
    calls = []
    env = functions('stop_rule_run', _e2e_lock=threading.RLock(),
        SESSION=SimpleNamespace(snapshot=lambda:current),
        stop_e2e=lambda:calls.append(True) or {'ok':True,'state':'stopping'})
    for data in (None, {}, {'run_id':'old'}):
        with pytest.raises(ValueError): env['stop_rule_run'](data)
    current['kind'] = 'sensor-rig'
    with pytest.raises(ValueError): env['stop_rule_run']({'run_id':'new'})
    assert not calls
    current['kind'] = 'rule-run'
    assert env['stop_rule_run']({'run_id':'new'})['state'] == 'stopping'
    current['state'] = 'completed'
    assert env['stop_rule_run']({'run_id':'new'})['state'] == 'completed'
    assert len(calls) == 1


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


@pytest.mark.parametrize('state,code', [('stopping', 1), ('stopping', -11), ('running', 130)])
def test_stop_request_cannot_hide_worker_failure(tmp_path, state, code):
    import threading
    import time
    calls = []
    process = SimpleNamespace(pid=123, wait=lambda: code)
    job = {'kind': 'run', 'state': state, 'results': None}
    env = functions('_finish_e2e', _e2e_process=process, _e2e_job=job,
        SESSION=SimpleNamespace(transition=lambda state, **kw: calls.append((state, kw))),
        restore_editor_world=lambda: None, _e2e_pid=tmp_path/'pid',
        _e2e_lock=threading.RLock(), Path=Path, time=time)
    env['_finish_e2e'](process)
    assert job['state'] == 'failed'
    assert calls[-1][0] == 'failed'
    assert calls[-1][1]['outcome']['failure_category'] == 'process_exit'
    assert calls[-1][1]['returncode'] == code


def test_cancelled_rule_partial_result_is_not_assessed_as_completed_benchmark(tmp_path):
    import threading
    import time
    result = tmp_path / 'stopped.json'
    result.write_text('{"status":"stopped","elapsed_s":0}')
    calls = []
    process = SimpleNamespace(pid=123, wait=lambda: 0)
    job = {'kind': 'rule-run', 'state': 'stopping', 'results': str(result)}
    def must_not_assess(*args):
        raise AssertionError('Cancelled task is not a completed benchmark')
    env = functions('_finish_e2e', _benchmark_result_failed=must_not_assess,
        _e2e_process=process, _e2e_job=job, Path=Path, time=time,
        _e2e_pid=tmp_path/'pid', _e2e_lock=threading.RLock(), restore_editor_world=lambda: None,
        SESSION=SimpleNamespace(transition=lambda state, **kw: calls.append((state, kw))))
    env['_finish_e2e'](process)
    assert calls[-1][0] == 'stopped'
    outcome = calls[-1][1]['outcome']
    assert outcome['result_assessed'] is False
    assert outcome['benchmark_failed'] is False and outcome['failure_category'] is None


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
    weather=SimpleNamespace(**{k:float(i) for i,k in enumerate(('cloudiness','precipitation','precipitation_deposits',
        'wind_intensity','sun_azimuth_angle','sun_altitude_angle','fog_density','fog_distance',
        'fog_falloff','wetness','scattering_intensity','mie_scattering_scale',
        'rayleigh_scattering_scale','dust_storm'))})
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
    assert result['weather']==vars(weather)


@pytest.mark.parametrize('action,expected', [('run', True), ('preset-run', True),
                                           ('sensor-rig', True), ('rule-run', True), ('doctor', False), ('model-smoke', False)])
def test_all_world_executions_capture_editor_scene_before_mutation(action, expected):
    source = Path(__file__).resolve().parents[1]/'tools/livery_bridge.py'
    tree = ast.parse(source.read_text())
    start = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'start_e2e')
    assignment = next(n for n in ast.walk(start) if isinstance(n, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == 'starting_scene' for t in n.targets))
    calls = []
    snapshot = {'map':'Town04', 'objects':[{'stable_id':'user-object'}]}
    env = {'action':action, 'capture_scene_document':lambda:calls.append(True) or snapshot}
    exec(compile(ast.Module(body=[assignment], type_ignores=[]), str(source), 'exec'), env)
    assert env['starting_scene'] == (snapshot if expected else None)
    assert bool(calls) is expected
    first_write = next(n for n in ast.walk(start) if isinstance(n, ast.Assign)
                       and any(isinstance(t, ast.Name) and t.id == 'log_stream' for t in n.targets))
    assert assignment.lineno < first_write.lineno


def test_promote_experiment_snapshot_reuses_scene_store_without_world_access(tmp_path):
    from carla_safety_agent.scene_store import SceneStore, validate_scene
    original = {'map':'Town04', 'objects':[]}
    scenes = SceneStore(tmp_path)
    env = functions('save_experiment_scene', validate_scene=validate_scene, SCENES=scenes,
        SESSION=SimpleNamespace(read_execution=lambda _: {'run_id':'experiment-1',
            'configuration':{'starting_scene':original}}))
    result = env['save_experiment_scene']({'run_id':'experiment-1', 'name':'Recovered snapshot'})
    assert result['world_modified'] is False
    saved = scenes.read(result['head']['scene_id'])['document']
    assert saved['source_execution'] == {'run_id':'experiment-1', 'scope':'pre_execution_editor'}
    assert saved['map'] == 'Town04'
    assert 'source_execution' not in original
    env['SESSION'] = SimpleNamespace(read_execution=lambda _: {'configuration':{}})
    with pytest.raises(ValueError, match='no recorded starting scene'):
        env['save_experiment_scene']({'run_id':'legacy'})


@pytest.mark.parametrize('accepted,residual', [(False, True), (True, True), (True, False)])
def test_delete_requires_native_acceptance_and_fresh_snapshot(accepted, residual):
    calls = []
    actor = SimpleNamespace(type_id='static.prop.test', destroy=lambda:accepted)
    def lookup(_):
        return actor if not calls or residual else None
    def fresh(_):
        calls.append('fresh')
        return SimpleNamespace(find=lambda _:actor if residual else None)
    world = SimpleNamespace(id=1,get_actor=lookup, wait_for_tick=fresh)
    names = {7:'test'}
    env = functions('delete_actor', evaluation_active=lambda:False, connect_world=lambda:world,
                    _actor_object_names=names, _generated_actor_assets={}, _editor_actors={7})
    if accepted and not residual:
        assert env['delete_actor'](7)['ok']
        assert names == {} and calls == ['fresh']
    else:
        with pytest.raises(RuntimeError): env['delete_actor'](7)
        assert names == {7:'test'}
        assert calls == (['fresh'] if accepted else [])


@pytest.mark.parametrize('fault',['missing_snapshot','changed_world'])
def test_uncertain_delete_retains_local_identity(fault):
    actor=SimpleNamespace(type_id='static.prop.test',destroy=lambda:True)
    world=SimpleNamespace(id=1,get_actor=lambda _:actor,
        wait_for_tick=lambda _:None if fault=='missing_snapshot' else SimpleNamespace(find=lambda _:None))
    worlds=iter([world,SimpleNamespace(id=2)])
    names={7:'test'}; assets={7:'generated.prop.test'}; owned={7}
    env=functions('delete_actor',evaluation_active=lambda:False,connect_world=lambda:next(worlds),
        _actor_object_names=names,_generated_actor_assets=assets,_editor_actors=owned)
    with pytest.raises(RuntimeError,match='uncertain'):env['delete_actor'](7)
    assert names=={7:'test'} and assets=={7:'generated.prop.test'} and owned=={7}


def test_delete_backup_failure_prevents_native_destruction():
    def forbidden():pytest.fail('Deletion reached native destroy before durable backup')
    actor=SimpleNamespace(type_id='static.prop.test',destroy=forbidden)
    world=SimpleNamespace(get_actor=lambda _:actor)
    def fail(*_):raise ValueError('snapshot write failed')
    env=functions('delete_actor',evaluation_active=lambda:False,connect_world=lambda:world,
                  backup_managed_deletion=fail)
    with pytest.raises(ValueError,match='snapshot write failed'):env['delete_actor'](7)


@pytest.mark.parametrize('fault',[None,'world','missing'])
def test_managed_deletion_backup_is_saved_before_return(fault):
    calls=[]; world=SimpleNamespace(id=1); actor=SimpleNamespace()
    document={'objects':[] if fault=='missing' else [{'stable_id':'stable-one'}]}
    head={'scene_id':'backup-one','version':'version-one'}
    env=functions('backup_managed_deletion',position_history_identity=lambda *_:{'stable_id':'stable-one'},
        capture_scene_document=lambda:document,connect_world=lambda:SimpleNamespace(id=2 if fault=='world' else 1),
        SCENES=SimpleNamespace(save=lambda doc,name:(calls.append((doc,name)) or {'head':head})))
    if fault:
        with pytest.raises(ValueError):env['backup_managed_deletion'](world,actor)
        assert not calls
    else:
        assert env['backup_managed_deletion'](world,actor)=={**head,'stable_id':'stable-one'}
        assert calls[0][0] is document


def test_live_scene_bindings_ignore_dead_history_and_use_one_snapshot():
    calls = []
    actor = SimpleNamespace(id=8, type_id='static.prop.test')
    def snapshot():
        calls.append('snapshot')
        return SimpleNamespace(find=lambda n:object() if n==8 else None)
    world = SimpleNamespace(get_snapshot=snapshot,get_actor=lambda n:actor)
    record = {'origin':'user','stable_id':'stable','type_id':actor.type_id}
    env = functions('live_scene_bindings')
    assert env['live_scene_bindings'](world, {'7':record,'8':record}) == {'stable':actor}
    assert calls == ['snapshot']


@pytest.mark.parametrize('failure', ['duplicate','missing','wrong-type','disappeared'])
def test_live_scene_bindings_reject_ambiguous_or_changed_actors(failure):
    actor = SimpleNamespace(id=8,type_id='static.prop.test')
    record = {'origin':'user','stable_id':'stable','type_id':actor.type_id}
    records = {'8':record}
    if failure=='duplicate': records['9']=dict(record)
    if failure=='missing': record.pop('stable_id')
    if failure=='wrong-type': record['type_id']='vehicle.other'
    world = SimpleNamespace(get_snapshot=lambda:SimpleNamespace(find=lambda _:object()),
                            get_actor=lambda _:None if failure=='disappeared' else actor)
    with pytest.raises(RuntimeError): functions('live_scene_bindings')['live_scene_bindings'](world,records)


def test_generated_run_results_are_distinct_for_identical_routes(tmp_path):
    import uuid
    source=Path(__file__).resolve().parents[1]/'tools/livery_bridge.py'
    tree=ast.parse(source.read_text())
    start=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='start_e2e')
    assignment=next(n for n in ast.walk(start) if isinstance(n,ast.Assign)
                    and any(isinstance(t,ast.Name) and t.id=='results_path' for t in n.targets))
    env={'action':'run','PROJECT_ROOT':tmp_path,'route':Path('same-plan.json'),'uuid':uuid}
    code=compile(ast.Module(body=[assignment],type_ignores=[]),str(source),'exec')
    exec(code,env)
    first=env['results_path']
    first.parent.mkdir(parents=True)
    first.write_text('previous result')
    exec(code,env)
    assert env['results_path']!=first
    assert env['results_path'].parent==tmp_path/'runs/uniad'
    assert first.read_text()=='previous result'


def test_compile_exposes_review_of_exact_archived_configuration(tmp_path):
    from dataclasses import replace
    from carla_safety_agent.natural_language import NaturalLanguageCompiler
    from carla_safety_agent.scenario_archive import archive_scenario, read_verified_scenario
    from carla_safety_agent.build_plan import build_plan
    import math
    env=functions('compile_scenario',NaturalLanguageCompiler=NaturalLanguageCompiler, math=math,
                  replace=replace,PROJECT_ROOT=tmp_path,archive_scenario=archive_scenario,build_plan=build_plan)
    result=env['compile_scenario']({'description':'Town04 前车急刹，自车 5 m/s','max_duration_s':2})
    document,digest=read_verified_scenario(result['scenario_path'])
    assert result['plan_review']['scenario_sha256']==digest
    assert result['plan_review']['oracle']==document['oracle']
    assert result['plan_review']['environment']==document['environment']
    assert result['plan_review']['oracle']['max_duration_s']==2
    assert result['build_plan']['map_name']==document['map_name']
    assert result['build_plan']['trigger']['action']=='hard_brake'
    assert result['plan_review']['limitations']


@pytest.mark.parametrize('invalid', [
    {'description':None}, {'description':' '}, {'description':'x'*10001},
    {'seed':True}, {'seed':1.5}, {'seed':'7'}, {'seed':-1}, {'seed':2**32},
    {'max_duration_s':False}, {'max_duration_s':-1}, {'max_duration_s':0},
    {'max_duration_s':'2'}, {'max_duration_s':float('nan')}, {'max_duration_s':float('inf')},
])
def test_compile_invalid_options_fail_before_compiler_or_archive(invalid):
    import math
    env=functions('compile_scenario',math=math)
    with pytest.raises(ValueError):
        env['compile_scenario']({'description':'Town04 前车急刹',**invalid})


def test_reviewed_plan_executes_exact_archive_without_recompilation():
    calls=[]
    env=functions('execute_reviewed_scenario',start_e2e=lambda value:calls.append(value) or {'ok':True})
    payload={'confirmed':True,'scenario_path':'/local/plan.json','scenario_sha256':'a'*64}
    assert env['execute_reviewed_scenario'](payload)['ok']
    assert calls==[{'action':'run','algorithm':'uniad-tiny','route':'/local/plan.json',
                   'scenario_sha256':'a'*64,'confirmed':True,'unified_capture':False}]
    for patch in ({'confirmed':False},{'confirmed':'true'},{'scenario_sha256':'invalid'},
                  {'scenario_sha256':'A'*64},{'scenario_path':None}):
        with pytest.raises(ValueError): env['execute_reviewed_scenario']({**payload,**patch})
    assert len(calls)==1


@pytest.mark.parametrize('algorithm', ['uniad-tiny','uniad-base','vad','tcp','admlp'])
def test_reviewed_plan_preserves_selected_model_and_capture(algorithm):
    calls=[]
    env=functions('execute_reviewed_scenario',start_e2e=lambda value:calls.append(value) or {'ok':True})
    payload={'confirmed':True,'scenario_path':'/local/plan.json','scenario_sha256':'a'*64,
             'algorithm':algorithm,'unified_capture':True}
    env['execute_reviewed_scenario'](payload)
    assert calls[0]['algorithm']==algorithm and calls[0]['unified_capture'] is True
    for patch in ({'algorithm':'unknown'},{'unified_capture':'false'}):
        with pytest.raises(ValueError): env['execute_reviewed_scenario']({**payload,**patch})
    assert len(calls)==1


@pytest.mark.parametrize('data,expected', [({},'1'),({'unified_capture':True},'1'),({'unified_capture':False},'0')])
def test_model_capture_option_reaches_child_environment(data, expected):
    source=Path(__file__).resolve().parents[1]/'tools/livery_bridge.py'
    tree=ast.parse(source.read_text())
    start=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='start_e2e')
    assignment=next(n for n in ast.walk(start) if isinstance(n,ast.Assign)
        and any(isinstance(t,ast.Name) and t.id=='model_capture' for t in n.targets))
    call=next(n for n in ast.walk(start) if isinstance(n,ast.Expr) and isinstance(n.value,ast.Call)
        and any(k.arg=='CSA_SENSOR_CAPTURE' for k in n.value.keywords))
    env={'data':data,'env':{},'E2E_ROOT':'root','UNIAD_PYTHON':'python',
         '_evaluation_control_dir':'control','DATASET_ROOT':'datasets'}
    exec(compile(ast.Module(body=[assignment,call],type_ignores=[]),str(source),'exec'),env)
    assert env['env']['CSA_SENSOR_CAPTURE']==expected

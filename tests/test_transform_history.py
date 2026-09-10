import copy
import json
import pytest
from carla_safety_agent.transform_history import TransformHistory,same_pose


IDENTITY={'episode':'18446744073709551615','actor_id':7,'type_id':'static.prop.test','stable_id':'stable-a'}


def pose(x):return {'location':{'x':x,'y':2.,'z':3.},'rotation':{'pitch':0.,'yaw':0.,'roll':0.}}


def record(store,a,b):
    row=store.begin(IDENTITY,'record',pose(a),pose(b))
    return store.finish(IDENTITY,row['pending']['id'],pose(b))


def test_persistent_multi_step_undo_redo(tmp_path):
    store=TransformHistory(tmp_path);record(store,1,2);row=record(store,2,3)
    store=TransformHistory(tmp_path)
    for kind,current,wanted,cursor in [('undo',3,2,1),('undo',2,1,0),('redo',1,2,1),('redo',2,3,2)]:
        row=store.begin(IDENTITY,kind,pose(current),expected_revision=row['revision'])
        assert row['pending']['target']==pose(wanted)
        row=store.finish(IDENTITY,row['pending']['id'],pose(wanted))
        assert row['cursor']==cursor and len(row['entries'])==2


def test_branch_keeps_old_archive_and_discards_redo_only(tmp_path):
    store=TransformHistory(tmp_path);record(store,1,2);row=record(store,2,3)
    row=store.begin(IDENTITY,'undo',pose(3),expected_revision=row['revision'])
    row=store.finish(IDENTITY,row['pending']['id'],pose(2));revision=row['revision']
    new=record(store,2,4)
    archived=json.loads((store.folder(IDENTITY)/(revision+'.json')).read_text())
    assert archived==row and len(new['entries'])==2
    assert new['entries'][-1]['after']==pose(4)


def test_external_move_starts_separate_chain_and_preserves_old(tmp_path):
    store=TransformHistory(tmp_path);old=record(store,1,2);row=record(store,8,9)
    assert len(row['entries'])==1 and row['entries'][0]['before']==pose(8)
    assert (store.folder(IDENTITY)/(old['revision']+'.json')).is_file()


def test_stale_revision_or_native_pose_never_advances_cursor(tmp_path):
    store=TransformHistory(tmp_path);row=record(store,1,2)
    for revision,current in [('old',2),(row['revision'],8)]:
        with pytest.raises(ValueError):store.begin(IDENTITY,'undo',pose(current),expected_revision=revision)
        assert store.read(IDENTITY)==row


def test_interrupted_intent_remains_blocked_after_restart(tmp_path):
    store=TransformHistory(tmp_path);row=store.begin(IDENTITY,'record',pose(1),pose(2))
    store=TransformHistory(tmp_path)
    with pytest.raises(ValueError,match='inspection'):store.begin(IDENTITY,'record',pose(2),pose(3))
    with pytest.raises(ValueError):store.finish(IDENTITY,row['pending']['id'],pose(1))
    row=store.fail(IDENTITY,row['pending']['id'],'native timeout')
    with pytest.raises(ValueError):store.finish(IDENTITY,row['pending']['id'],pose(2))
    with pytest.raises(ValueError):store.acknowledge(IDENTITY,row['revision'],row['pending']['id'],1)
    final=store.acknowledge(IDENTITY,row['revision'],row['pending']['id'],True)
    assert final['entries']==[] and final['pending'] is None
    assert (store.folder(IDENTITY)/(row['revision']+'.json')).exists()


@pytest.mark.parametrize('damage',['cursor','identity','duplicate','chain','pending'])
def test_corrupt_history_preserved_and_rejected(tmp_path,damage):
    store=TransformHistory(tmp_path);row=record(store,1,2);path=store.folder(IDENTITY)/'current.json'
    if damage=='cursor':row['cursor']=True
    elif damage=='identity':row['identity']['actor_id']=8
    elif damage=='duplicate':row['entries'].append(copy.deepcopy(row['entries'][0]))
    elif damage=='chain':row['entries'].append({**row['entries'][0],'id':'other','before':pose(8)})
    else:row['pending']={'id':'pending','kind':'undo','state':'attempting','source':pose(2),'target':pose(9)}
    path.write_text(json.dumps(row));raw=path.read_bytes()
    with pytest.raises(ValueError):store.read(IDENTITY)
    assert path.read_bytes()==raw


def test_linked_current_file_refused(tmp_path):
    store=TransformHistory(tmp_path);folder=store.folder(IDENTITY);folder.mkdir()
    (folder/'current.json').symlink_to(tmp_path/'missing')
    with pytest.raises(ValueError):store.read(IDENTITY)


def test_intent_is_durable_before_native_work_and_failed_publication_preserves_it(tmp_path,monkeypatch):
    store=TransformHistory(tmp_path);row=store.begin(IDENTITY,'record',pose(1),pose(2))
    def fail(*args):raise OSError('disk error')
    monkeypatch.setattr('carla_safety_agent.transform_history.atomic',fail)
    with pytest.raises(OSError):store.finish(IDENTITY,row['pending']['id'],pose(2))
    assert TransformHistory(tmp_path).read(IDENTITY)==row


def test_pose_wrapping_and_independent_runtime_actor_identity(tmp_path):
    a=pose(1);b=pose(1);b['rotation']['yaw']=360
    assert same_pose(a,b)
    store=TransformHistory(tmp_path);record(store,1,2)
    assert store.read(IDENTITY|{'actor_id':8})['entries']==[]
    assert store.read(IDENTITY|{'episode':'1'})['entries']==[]


@pytest.mark.parametrize('failure',['setter','snapshot','drift'])
def test_native_failure_records_inspection_without_automatic_rollback(tmp_path,failure):
    from types import SimpleNamespace as NS
    from test_studio_bridge import functions
    store=TransformHistory(tmp_path);calls=[]
    current=NS(location=NS(x=1.,y=2.,z=3.),rotation=NS(pitch=0.,yaw=0.,roll=0.))
    def set_transform(target):
        nonlocal current
        calls.append(target)
        if failure=='setter':raise RuntimeError('Injected native failure')
        current=target
        if failure=='drift':current.location.x+=1
    actor=NS(id=7,type_id=IDENTITY['type_id'],get_transform=lambda:current,set_transform=set_transform)
    world=NS(id=2**64-1,get_settings=lambda:NS(synchronous_mode=False),get_actors=lambda:NS(filter=lambda _:[]),
        wait_for_tick=lambda _:None if failure=='snapshot' else NS(frame=1,find=lambda _:True),get_actor=lambda _:actor)
    carla=NS(Location=lambda **v:NS(**v),Rotation=lambda **v:NS(**v),Transform=lambda loc,rot:NS(location=loc,rotation=rot))
    env=functions('apply_position_history','transform_record',POSITION_HISTORY=store,carla=carla,
        require_asset_import_idle=lambda:None,connect_world=lambda:world,position_history_identity=lambda *_:IDENTITY)
    with pytest.raises((ValueError,RuntimeError)):
        env['apply_position_history'](world,actor,IDENTITY,'record',pose(2))
    row=store.read(IDENTITY)
    assert len(calls)==1 and row['pending']['state']=='needs_attention' and row['cursor']==0


def test_failed_intent_write_never_calls_native_setter(tmp_path,monkeypatch):
    from types import SimpleNamespace as NS
    from test_studio_bridge import functions
    store=TransformHistory(tmp_path)
    current=NS(location=NS(x=1.,y=2.,z=3.),rotation=NS(pitch=0.,yaw=0.,roll=0.))
    actor=NS(get_transform=lambda:current,set_transform=lambda _:pytest.fail('No durable intent'))
    world=NS(get_settings=lambda:NS(synchronous_mode=False),get_actors=lambda:NS(filter=lambda _:[]))
    def fail(*args):raise OSError('disk failure')
    monkeypatch.setattr('carla_safety_agent.transform_history.atomic',fail)
    env=functions('apply_position_history','transform_record',POSITION_HISTORY=store,require_asset_import_idle=lambda:None)
    with pytest.raises(OSError):env['apply_position_history'](world,actor,IDENTITY,'record',pose(2))


def test_post_publication_error_does_not_overwrite_completed_history(tmp_path,monkeypatch):
    from carla_safety_agent.scene_store import atomic
    store=TransformHistory(tmp_path);row=store.begin(IDENTITY,'record',pose(1),pose(2))
    def fail_after_write(path,payload):atomic(path,payload);raise OSError('directory sync acknowledgement lost')
    monkeypatch.setattr('carla_safety_agent.transform_history.atomic',fail_after_write)
    with pytest.raises(OSError):store.finish(IDENTITY,row['pending']['id'],pose(2))
    with pytest.raises(ValueError):store.fail(IDENTITY,row['pending']['id'],'previous error')
    assert store.read(IDENTITY)['cursor']==1 and store.read(IDENTITY)['pending'] is None


def test_active_evaluation_does_not_connect_for_history():
    from test_studio_bridge import functions
    env=functions('position_history_status',evaluation_active=lambda:True,
        connect_world=lambda:pytest.fail('Competing with tick owner'))
    assert env['position_history_status'](7)['eligible'] is False


def test_delayed_native_snapshot_observes_without_resending_transform(tmp_path):
    from types import SimpleNamespace as NS
    from test_studio_bridge import functions
    store=TransformHistory(tmp_path);calls=[];ticks=[]
    old=NS(location=NS(x=1.,y=2.,z=3.),rotation=NS(pitch=0.,yaw=0.,roll=0.))
    def snapshot(timeout):
        ticks.append(len(ticks)+1)
        return NS(frame=len(ticks),find=lambda _:True)
    actor=NS(id=7,type_id=IDENTITY['type_id'],get_transform=lambda:old if len(ticks)<2 else calls[0],set_transform=lambda target:calls.append(target))
    world=NS(id=2**64-1,get_settings=lambda:NS(synchronous_mode=False),get_actors=lambda:NS(filter=lambda _:[]),
        wait_for_tick=snapshot,get_actor=lambda _:actor)
    carla=NS(Location=lambda **v:NS(**v),Rotation=lambda **v:NS(**v),Transform=lambda loc,rot:NS(location=loc,rotation=rot))
    env=functions('apply_position_history','transform_record',POSITION_HISTORY=store,carla=carla,
        require_asset_import_idle=lambda:None,connect_world=lambda:world,position_history_identity=lambda *_:IDENTITY)
    result=env['apply_position_history'](world,actor,IDENTITY,'record',pose(2))
    assert result['cursor']==1 and not result['pending']
    assert len(calls)==1 and ticks==[1,2,3]

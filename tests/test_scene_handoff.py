import json
import threading
import pytest
from carla_safety_agent.scene_handoff import SceneHandoff


def test_map_enumeration_can_use_short_names_without_prefix_guessing():
    from carla_safety_agent.scene_handoff import available_map
    assert available_map('Carla/Maps/Town05',['Town04','Town05_Opt','Town05'])=='Town05'
    assert available_map('Carla/Maps/Town05',['/Game/Carla/Maps/Town05'])=='/Game/Carla/Maps/Town05'
    for maps in (['Town05_Opt'],['Town05','/Game/Carla/Maps/Town05']):
        with pytest.raises(ValueError):available_map('Carla/Maps/Town05',maps)


def fixture(tmp_path):
    handoff=SceneHandoff(tmp_path/'handoff',clock=lambda:100)
    source={'map':'Town04','objects':[]};target={'map':'Town05','objects':[]}
    selection={'scene_id':'scene','version':'version'}
    review=handoff.preview(selection,target,source,2**63+5,[])
    return handoff,source,target,selection,review


@pytest.mark.parametrize('change',['episode','source','target','inventory','expired','confirmation'])
def test_review_is_exact_single_use_and_never_changes_world(tmp_path,change):
    h,source,target,selection,review=fixture(tmp_path)
    data={'review_token':review['review_token'],'confirmed':True};episode=2**63+5;inventory=[]
    if change=='episode':episode+=1
    if change=='source':source={**source,'weather':{'fog':1}}
    if change=='target':target={**target,'weather':{'fog':1}}
    if change=='inventory':inventory=[{'id':1}]
    if change=='expired':h.clock=lambda:221
    if change=='confirmation':data['confirmed']=1
    with pytest.raises(ValueError):h.consume(data,target,source,episode,inventory)
    assert h.status()['state']=='idle' and not h.path.exists()
    if change!='confirmation':
        with pytest.raises(ValueError):h.selection(review['review_token'])


def test_journal_gates_restart_and_requires_explicit_inactive_ack(tmp_path):
    h,source,target,selection,review=fixture(tmp_path)
    assert h.consume({'review_token':review['review_token'],'confirmed':True},target,source,2**63+5,[])==selection
    row=h.begin(review,{'scene_id':'backup','version':'v1'})
    with pytest.raises(ValueError):h.require_idle()
    with pytest.raises(ValueError):h.acknowledge({'request_id':row['request_id'],'confirmed':True})
    restarted=SceneHandoff(h.root)
    assert restarted.status()['state']=='needs_attention'
    with pytest.raises(ValueError):restarted.require_idle()
    for invalid in ({'request_id':'wrong','confirmed':True},{'request_id':row['request_id'],'confirmed':1}):
        with pytest.raises(ValueError):restarted.acknowledge(invalid)
    acknowledged=restarted.acknowledge({'request_id':row['request_id'],'confirmed':True})
    assert acknowledged['state']=='acknowledged';restarted.require_idle()
    assert acknowledged['backup']=={'scene_id':'backup','version':'v1'}


def test_owner_bypass_is_thread_local_and_history_retained(tmp_path):
    h,_,_,_,review=fixture(tmp_path);row=h.begin(review,{'scene_id':'backup','version':'v1'})
    errors=[]
    def other():
        try:h.require_idle()
        except ValueError:errors.append('blocked')
    with h.owner_scope():
        h.require_idle();thread=threading.Thread(target=other);thread.start();thread.join()
    assert errors==['blocked']
    h.update(row['request_id'],state='restored',phase='verified');h.worker_active=False
    h.begin(review,{'scene_id':'backup2','version':'v2'})
    assert json.loads((h.root/(row['request_id']+'.json')).read_text())['state']=='restored'


@pytest.mark.parametrize('change',[{'state':'idle'},{'phase':'unknown'},{'selection':{}},{'backup':{}},
    {'source_episode':True},{'started_at':float('nan')}])
def test_corrupt_gate_cannot_be_treated_as_idle(tmp_path,change):
    h,_,_,_,review=fixture(tmp_path);h.begin(review,{'scene_id':'backup','version':'v1'})
    row=json.loads(h.path.read_text());row.update(change);h.path.write_text(json.dumps(row))
    with pytest.raises(ValueError):h.require_idle()


def test_linked_gate_cannot_be_treated_as_idle(tmp_path):
    h,_,_,_,review=fixture(tmp_path);h.begin(review,{'scene_id':'backup','version':'v1'})
    content=h.path.read_bytes();h.path.unlink();other=tmp_path/'other.json';other.write_bytes(content);h.path.symlink_to(other)
    with pytest.raises(ValueError):h.require_idle()


@pytest.mark.parametrize('fault',[None,'changed_before','load_timeout','restore'])
def test_native_handoff_does_not_automatically_reload_after_failure(tmp_path,monkeypatch,fault):
    from types import SimpleNamespace
    from test_studio_bridge import functions
    h,source,target,_,review=fixture(tmp_path)
    row=h.begin(review,{'scene_id':'backup','version':'v1'});loads=[]
    class Actors(list):
        def filter(self,_):return []
    world=SimpleNamespace(id=2**63+5,get_settings=lambda:SimpleNamespace(synchronous_mode=False),
        get_actors=lambda:Actors(),get_map=lambda:SimpleNamespace(name='Town04'))
    def load(name):
        loads.append(name)
        if fault=='load_timeout':raise TimeoutError('load outcome uncertain')
        world.id=3;world.get_map=lambda:SimpleNamespace(name='Town05');return world
    client=SimpleNamespace(load_world=load,set_timeout=lambda _:None)
    def restore(_):
        if fault=='restore':raise ValueError('target material unavailable')
        return {'bindings':{},'restored':0}
    monkeypatch.setattr('carla_safety_agent.world_health.observe_idle',lambda *_:{'episode':3,'synchronous':False,'sensors':0})
    env=functions('perform_scene_handoff',HANDOFF=h,_simulation_lock=threading.RLock(),
        connect_world=lambda:world,require_idle_native_world=lambda _:None,
        capture_scene_document=lambda:{**source,'changed':True} if fault=='changed_before' else source,
        _provenance=SimpleNamespace(records=lambda _:{}),_carla_client=client,restore_scene_document=restore)
    env['perform_scene_handoff'](row,{'document':target},source,[],'Town05')
    assert loads==([] if fault=='changed_before' else ['Town05'])
    expected='failed_before_switch' if fault=='changed_before' else 'needs_attention' if fault else 'restored'
    assert h.status()['state']==expected and not h.worker_active
    if expected=='needs_attention':
        with pytest.raises(ValueError):h.require_idle()


def test_waiting_editor_request_cannot_target_replacement_episode(tmp_path):
    from functools import wraps
    from test_studio_bridge import functions
    lock=threading.Lock();waiting=threading.Event();errors=[];calls=[]
    class Gate:
        def __enter__(self):waiting.set();lock.acquire()
        def __exit__(self,*_):lock.release()
    h=SceneHandoff(tmp_path/'handoff')
    env=functions('simulation_operation',wraps=wraps,HANDOFF=h,_simulation_lock=Gate(),_world_episode=1)
    def edit():calls.append('mutated')
    guarded=env['simulation_operation'](edit)
    def request():
        try:guarded()
        except ValueError as exc:errors.append(str(exc))
    lock.acquire();thread=threading.Thread(target=request);thread.start();assert waiting.wait(2)
    env['_world_episode']=2;lock.release();thread.join(2)
    assert not calls and len(errors)==1 and 'World changed' in errors[0]

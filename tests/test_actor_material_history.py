import json
from types import SimpleNamespace
import pytest
from carla_safety_agent.actor_material_history import apply_with_history


def test_returned_rollback_does_not_authorize_overwriting_unresolved_actor(tmp_path):
    identity=dict(episode='1',actor_id=2,stable_id='abc',blueprint_id='vehicle.audi.a2',component='VehicleMesh',slot=4)
    def failed():
        raise RuntimeError('native failure')
    with pytest.raises(RuntimeError):
        apply_with_history(tmp_path,identity,None,'a'*64,
                           SimpleNamespace(apply=failed,rollback=lambda:None))
    before={p.name:p.read_bytes() for p in tmp_path.glob('*.json')}
    with pytest.raises(ValueError,match='unresolved operation'):
        apply_with_history(tmp_path,identity,None,'b'*64,
                           SimpleNamespace(apply=lambda:pytest.fail('must not apply')))
    assert before=={p.name:p.read_bytes() for p in tmp_path.glob('*.json')}


@pytest.mark.parametrize('fail',[False,True])
def test_write_ahead_and_failure(tmp_path,fail):
    identity=dict(episode='1',actor_id=2,stable_id='abc',blueprint_id='vehicle.audi.a2',component='VehicleMesh',slot=4)
    calls=[]
    def apply():
        row=json.loads(next(tmp_path.glob('*.json')).read_text())
        assert row['state']=='attempting' and row['identity']==identity
        calls.append('apply')
        if fail:raise RuntimeError('native failure')
    transaction=SimpleNamespace(apply=apply,rollback=lambda:calls.append('rollback'))
    if fail:
        with pytest.raises(RuntimeError,match='requires inspection'):
            apply_with_history(tmp_path,identity,None,'a'*64,transaction)
    else:apply_with_history(tmp_path,identity,None,'a'*64,transaction)
    row=json.loads(next(tmp_path.glob('*.json')).read_text())
    assert row['state']==('needs_attention' if fail else 'confirmed')
    assert calls==(['apply','rollback'] if fail else ['apply'])
    assert row['undo_supported'] is False


@pytest.mark.parametrize('fail_at',[1,2])
def test_journal_failure_does_not_claim_success(tmp_path,monkeypatch,fail_at):
    import carla_safety_agent.actor_material_history as module
    identity=dict(episode='1',actor_id=2,stable_id='abc',blueprint_id='walker.pedestrian.0001',component='CharacterMesh0',slot=14)
    original=module.atomic;writes=[];calls=[]
    def atomic(path,row):
        writes.append(row['state'])
        if len(writes)==fail_at:raise OSError('disk error')
        original(path,row)
    monkeypatch.setattr(module,'atomic',atomic)
    with pytest.raises((OSError,RuntimeError)):
        apply_with_history(tmp_path,identity,None,'a'*64,SimpleNamespace(apply=lambda:calls.append('apply'),rollback=lambda:calls.append('rollback')))
    assert calls==([] if fail_at==1 else ['apply'])
    if fail_at==2:assert json.loads(next(tmp_path.glob('*.json')).read_text())['state']=='attempting'


def test_transition_identity_revision_and_failure(tmp_path):
    from carla_safety_agent.actor_material_history import ActorMaterialHistory
    identity=dict(episode='1',actor_id=2,stable_id='abc',blueprint_id='vehicle.audi.a2',component='VehicleMesh',slot=4)
    op=apply_with_history(tmp_path,identity,None,'a'*64,SimpleNamespace(apply=lambda:None))
    history=ActorMaterialHistory(tmp_path);current=['a'*64];calls=[]
    def verify(i,source,target):
        assert i==identity
        if current[0]!=source:raise ValueError('Current texture changed')
    def apply(i,target):
        assert history.read(op)['pending']['state']=='attempting'
        current[0]=target;calls.append(target)
    undone=history.transition(op,'undo',op,verify,apply)
    assert current[0] is None and undone['applied'] is False
    with pytest.raises(ValueError):history.transition(op,'redo',op,verify,apply)
    redone=history.transition(op,'redo',undone['revision'],verify,apply)
    assert current[0]=='a'*64 and len(calls)==2
    def fail(i,target):raise RuntimeError('native failure')
    with pytest.raises(RuntimeError):history.transition(op,'undo',redone['revision'],verify,fail)
    assert history.read(op)['pending']['state']=='needs_attention'
    with pytest.raises(ValueError):history.transition(op,'undo',redone['revision'],verify,apply)


def transition_fixture(tmp_path):
    from carla_safety_agent.actor_material_history import ActorMaterialHistory
    identity=dict(episode='1',actor_id=2,stable_id='abc',blueprint_id='vehicle.audi.a2',component='VehicleMesh',slot=4)
    op=apply_with_history(tmp_path,identity,None,'a'*64,SimpleNamespace(apply=lambda:None))
    return ActorMaterialHistory(tmp_path),op


def failed_transition_fixture(tmp_path):
    history,op=transition_fixture(tmp_path)
    def fail(*_):raise RuntimeError('Uncertain native result')
    with pytest.raises(RuntimeError):history.transition(op,'undo',op,lambda *_:None,fail)
    return history,op,history.inspect(op,lambda _:None)['inspection_token']


def test_concurrent_recovery_only_one_write(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    history,op,token=failed_transition_fixture(tmp_path)
    original=history.read(op)['pending'];barrier=Barrier(2);calls=[]
    def worker():
        barrier.wait(timeout=5)
        try:
            history.recover(op,token,'target',None,lambda *_:None,lambda *_:calls.append('apply'))
            return 'confirmed'
        except ValueError:return 'rejected'
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(worker) for _ in range(2)]
        assert sorted(f.result(timeout=5) for f in futures)==['confirmed','rejected']
    row=history.read(op)
    assert calls==['apply'] and row['pending']==original and row['recovery']['state']=='confirmed'


@pytest.mark.parametrize('failure',['intent','commit','commit-and-error'])
def test_recovery_persistence_failure_preserves_original(tmp_path,monkeypatch,failure):
    import carla_safety_agent.material_history as protocol
    history,op,token=failed_transition_fixture(tmp_path)
    old=history.read(op);original=protocol.atomic;writes=[];calls=[]
    def atomic(path,row):
        writes.append(1);n=len(writes)
        if ((failure=='intent' and n==1) or (failure=='commit' and n==2)
                or (failure=='commit-and-error' and n>=2)):raise OSError('Injected recovery write failure')
        original(path,row)
    monkeypatch.setattr(protocol,'atomic',atomic)
    with pytest.raises((OSError,RuntimeError)):
        history.recover(op,token,'target',None,lambda *_:None,lambda *_:calls.append('apply'))
    row=history.read(op)
    assert row['state']==old['state'] and row['pending']==old['pending']
    if failure=='intent':assert not calls and 'recovery' not in row
    else:
        assert calls==['apply']
        assert row['recovery']['state']==('needs_attention' if failure=='commit' else 'attempting')
        fresh=history.inspect(op,lambda _:None)
        with pytest.raises(ValueError):history.recover(op,fresh['inspection_token'],'target',None,lambda *_:None,lambda *_:calls.append('again'))
        assert calls==['apply']


@pytest.mark.parametrize('current,match',[(None,'target'),('a'*64,'source'),('b'*64,'neither')])
def test_uncertain_transition_inspection_never_resolves(tmp_path,current,match):
    history,op=transition_fixture(tmp_path)
    def fail(*_):raise RuntimeError('Uncertain native result')
    with pytest.raises(RuntimeError):history.transition(op,'undo',op,lambda *_:None,fail)
    before=history.path(op).read_bytes()
    result=history.inspect(op,lambda _:current)
    assert result['source']=='a'*64 and result['target'] is None
    assert result['registry_matches']==match
    assert result['native_verified'] is False and result['automatic_retry_allowed'] is False
    assert result['pending']['state']=='needs_attention'
    assert history.path(op).read_bytes()==before


@pytest.mark.parametrize('choice,desired',[('source','a'*64),('target',None)])
def test_explicit_recovery_preserves_failure_and_blocks_repeat(tmp_path,choice,desired):
    history,op=transition_fixture(tmp_path)
    def fail(*_):raise RuntimeError('uncertain native edit')
    with pytest.raises(RuntimeError):history.transition(op,'undo',op,lambda *_:None,fail)
    old=history.read(op);calls=[]
    inspection=history.inspect(op,lambda _:None)
    result=history.recover(op,inspection['inspection_token'],choice,None,lambda *_:None,lambda _,target:calls.append(target))
    assert result['pending']==old['pending'] and result['state']==old['state']
    assert result['recovery']['state']=='confirmed' and result['recovery']['desired']==desired
    assert calls==[desired]
    fresh=history.inspect(op,lambda _:desired)
    with pytest.raises(ValueError):history.recover(op,fresh['inspection_token'],choice,desired,lambda *_:None,lambda *_:calls.append('again'))
    assert calls==[desired]


@pytest.mark.parametrize('failure',['stale-token','changed-registry','apply'])
def test_recovery_rejects_stale_or_uncertain_writes(tmp_path,failure):
    history,op=transition_fixture(tmp_path)
    def fail(*_):raise RuntimeError('native error')
    with pytest.raises(RuntimeError):history.transition(op,'undo',op,lambda *_:None,fail)
    inspection=history.inspect(op,lambda _:None);calls=[]
    def verify(*_):
        if failure=='changed-registry':raise ValueError('Registry changed')
    def apply(*_):calls.append('apply');raise RuntimeError('recovery failed')
    with pytest.raises((ValueError,RuntimeError)):
        history.recover(op,'stale' if failure=='stale-token' else inspection['inspection_token'],'target',None,verify,apply)
    row=history.read(op)
    if failure=='apply':assert calls==['apply'] and row['recovery']['state']=='needs_attention'
    else:assert not calls and 'recovery' not in row


def test_concurrent_transition_applies_only_once(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    history,op=transition_fixture(tmp_path);barrier=Barrier(2);calls=[]
    def worker():
        barrier.wait(timeout=5)
        try:
            history.transition(op,'undo',op,lambda *_:None,lambda *_:calls.append('apply'))
            return 'confirmed'
        except ValueError:return 'rejected'
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(worker) for _ in range(2)]
        assert sorted(f.result(timeout=5) for f in futures)==['confirmed','rejected']
    assert calls==['apply'] and len(history.read(op)['transitions'])==1


@pytest.mark.parametrize('failure',['intent','commit','commit-and-error'])
def test_transition_persistence_failure_retains_uncertainty(tmp_path,monkeypatch,failure):
    import carla_safety_agent.material_history as protocol
    history,op=transition_fixture(tmp_path);original=protocol.atomic;writes=[];calls=[]
    def atomic(path,row):
        writes.append(row)
        n=len(writes)
        if ((failure=='intent' and n==1) or (failure=='commit' and n==2)
                or (failure=='commit-and-error' and n>=2)):raise OSError('Injected persistence failure')
        original(path,row)
    monkeypatch.setattr(protocol,'atomic',atomic)
    with pytest.raises((OSError,RuntimeError)):
        history.transition(op,'undo',op,lambda *_:None,lambda *_:calls.append('apply'))
    row=history.read(op)
    assert row.get('applied',True) is True and not row.get('transitions')
    if failure=='intent':assert not calls and not row.get('pending')
    else:
        assert calls==['apply']
        assert row['pending']['state']==('needs_attention' if failure=='commit' else 'attempting')
        with pytest.raises(ValueError):history.transition(op,'undo',op,lambda *_:None,lambda *_:calls.append('again'))
        assert calls==['apply']

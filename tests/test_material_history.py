import pytest
from carla_safety_agent.material_history import MaterialHistory

IDENTITY=dict(episode='1',object_id='18446744073709551615',target='house',component='mesh',slot=2)

def test_durable_prior_override_and_restore(tmp_path):
    store=MaterialHistory(tmp_path)
    def apply():
        row=store.read(next(tmp_path.glob('*.json')).stem)
        assert row['state']=='attempting' and row['before']=='a'*64 and row['after'] is None
    operation=store.execute(IDENTITY,'a'*64,None,apply)
    assert MaterialHistory(tmp_path).read(operation)['state']=='confirmed'

def test_native_failure_remains_inspectable_without_retry(tmp_path):
    calls=[];store=MaterialHistory(tmp_path)
    def apply():calls.append(1);raise RuntimeError('native uncertain')
    with pytest.raises(RuntimeError,match='requires inspection'):store.execute(IDENTITY,None,'b'*64,apply)
    row=store.read(next(tmp_path.glob('*.json')).stem)
    assert calls==[1] and row['state']=='needs_attention' and row['after']=='b'*64

def test_invalid_or_linked_intent_never_applies(tmp_path):
    store=MaterialHistory(tmp_path/'history');calls=[]
    with pytest.raises(ValueError):store.execute(IDENTITY,'bad',None,lambda:calls.append(1))
    store.root.symlink_to(tmp_path,target_is_directory=True)
    with pytest.raises(ValueError):store.execute(IDENTITY,None,None,lambda:calls.append(1))
    assert calls==[]


def test_undo_redo_prior_hash_and_stale_revision(tmp_path):
    store=MaterialHistory(tmp_path);op=store.execute(IDENTITY,'a'*64,'b'*64,lambda:None)
    current=['b'*64];calls=[]
    def verify(identity,source,target):assert identity==IDENTITY and current[0]==source
    def apply(identity,target):
        assert store.read(op)['pending']['state']=='attempting'
        current[0]=target;calls.append(target)
    undone=store.transition(op,'undo',op,verify,apply)
    assert not undone['applied'] and current[0]=='a'*64
    with pytest.raises(ValueError):store.transition(op,'redo',op,verify,apply)
    done=MaterialHistory(tmp_path).transition(op,'redo',undone['revision'],verify,apply)
    assert done['applied'] and current[0]=='b'*64 and len(done['transitions'])==2
    assert calls==['a'*64,'b'*64]


def test_transition_verify_and_uncertain_apply(tmp_path):
    store=MaterialHistory(tmp_path);op=store.execute(IDENTITY,None,'b'*64,lambda:None)
    before=store.path(op).read_bytes()
    def refuse(*_):raise ValueError('external change')
    with pytest.raises(ValueError):store.transition(op,'undo',op,refuse,lambda *_:pytest.fail('no apply'))
    assert store.path(op).read_bytes()==before
    def fail(*_):raise RuntimeError('disconnected')
    with pytest.raises(RuntimeError,match='requires inspection'):store.transition(op,'undo',op,lambda *_:None,fail)
    assert store.read(op)['pending']['state']=='needs_attention'
    with pytest.raises(ValueError):store.transition(op,'undo',op,lambda *_:None,fail)


def test_two_concurrent_undo_requests_apply_once(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    store=MaterialHistory(tmp_path);op=store.execute(IDENTITY,None,'b'*64,lambda:None)
    barrier=Barrier(2);calls=[]
    def submit():
        barrier.wait(timeout=5)
        try:
            store.transition(op,'undo',op,lambda *_:None,lambda *_:calls.append(1))
            return 'done'
        except ValueError:return 'rejected'
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:submit(),range(2)))
    assert sorted(results)==['done','rejected'] and calls==[1]


@pytest.mark.parametrize('failure_call',[1,2])
def test_transition_disk_failure_never_claims_success(tmp_path,monkeypatch,failure_call):
    import carla_safety_agent.material_history as module
    store=MaterialHistory(tmp_path);op=store.execute(IDENTITY,None,'b'*64,lambda:None)
    original=module.atomic;writes=[];native=[]
    def atomic(path,row):
        writes.append(1)
        if len(writes)==failure_call:raise OSError('disk unavailable')
        original(path,row)
    monkeypatch.setattr(module,'atomic',atomic)
    with pytest.raises((OSError,RuntimeError)):
        store.transition(op,'undo',op,lambda *_:None,lambda *_:native.append(1))
    row=store.read(op)
    if failure_call==1:
        assert native==[] and 'pending' not in row
    else:
        assert native==[1] and row['pending']['state']=='needs_attention'
        assert row.get('applied',True) is True
        with pytest.raises(ValueError):store.transition(op,'undo',op,lambda *_:None,lambda *_:native.append(1))


def test_commit_and_failure_receipt_unwritable_leaves_durable_intent(tmp_path,monkeypatch):
    import carla_safety_agent.material_history as module
    store=MaterialHistory(tmp_path);op=store.execute(IDENTITY,None,'b'*64,lambda:None)
    original=module.atomic;writes=[];native=[]
    def atomic(path,row):
        writes.append(1)
        if len(writes)>1:raise OSError('disk unavailable')
        original(path,row)
    monkeypatch.setattr(module,'atomic',atomic)
    with pytest.raises(RuntimeError,match='journal failed'):
        store.transition(op,'undo',op,lambda *_:None,lambda *_:native.append(1))
    assert native==[1] and store.read(op)['pending']['state']=='attempting'
    with pytest.raises(ValueError):store.transition(op,'undo',op,lambda *_:None,lambda *_:native.append(1))


@pytest.mark.parametrize('current,expected',[(None,'source'),('b'*64,'target'),('c'*64,'neither')])
def test_inspection_is_read_only_and_never_resolves_native_uncertainty(tmp_path,current,expected):
    store=MaterialHistory(tmp_path)
    def fail():raise RuntimeError('native response lost')
    with pytest.raises(RuntimeError):store.execute(IDENTITY,None,'b'*64,fail)
    path=next(tmp_path.glob('*.json'));before=path.read_bytes()
    result=store.inspect(path.stem,lambda identity:current)
    assert result['registry_matches']==expected and result['state']=='needs_attention'
    assert result['native_verified'] is False and result['automatic_retry_allowed'] is False
    assert path.read_bytes()==before


def test_inspection_uses_pending_transition_direction(tmp_path):
    store=MaterialHistory(tmp_path);op=store.execute(IDENTITY,None,'b'*64,lambda:None)
    def fail(*_):raise RuntimeError('native response lost')
    with pytest.raises(RuntimeError):store.transition(op,'undo',op,lambda *_:None,fail)
    result=store.inspect(op,lambda _:None)
    assert result['source']=='b'*64 and result['target'] is None and result['registry_matches']=='target'
    assert store.read(op)['pending']['state']=='needs_attention'


def test_explicit_recovery_retains_failure_and_blocks_stale_retry(tmp_path):
    store=MaterialHistory(tmp_path)
    def fail():raise RuntimeError('original native error')
    with pytest.raises(RuntimeError):store.execute(IDENTITY,'a'*64,'b'*64,fail)
    op=next(tmp_path.glob('*.json')).stem
    observed=store.inspect(op,lambda _:'a'*64);calls=[]
    def verify(identity,current,desired):assert identity==IDENTITY and current=='a'*64 and desired=='b'*64
    def apply(identity,desired):
        assert store.read(op)['recovery']['state']=='attempting';calls.append(desired)
    with pytest.raises(ValueError):store.recover(op,'stale','target','a'*64,verify,apply)
    row=store.recover(op,observed['inspection_token'],'target','a'*64,verify,apply)
    assert row['state']=='needs_attention' and row['error']=='original native error'
    assert row['recovery']['state']=='confirmed' and calls==['b'*64]
    with pytest.raises(ValueError):store.recover(op,observed['inspection_token'],'target','a'*64,verify,apply)


def test_recovery_refuses_changed_registry_without_writing(tmp_path):
    store=MaterialHistory(tmp_path)
    with pytest.raises(RuntimeError):store.execute(IDENTITY,None,'b'*64,lambda:(_ for _ in ()).throw(RuntimeError('lost')))
    path=next(tmp_path.glob('*.json'));op=path.stem;before=path.read_bytes()
    inspection=store.inspect(op,lambda _:None)
    def verify(*_):raise ValueError('registry changed')
    with pytest.raises(ValueError):store.recover(op,inspection['inspection_token'],'source',None,verify,lambda *_:pytest.fail())
    assert path.read_bytes()==before

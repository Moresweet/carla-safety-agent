import pytest
from carla_safety_agent.copy_history import CopyHistory

SOURCE=dict(episode='1',actor_id=7,type_id='prop.test',stable_id=None)
TARGET=dict(episode='1',actor_id=8,type_id='prop.test',stable_id='new-object')

def test_write_ahead_and_restart_receipt(tmp_path):
    store=CopyHistory(tmp_path)
    def action():
        assert store.read(next(tmp_path.glob('*.json')).stem)['state']=='attempting'
        return {'ok':True,'object':{'id':8}}
    result=store.execute(SOURCE,action,lambda _:TARGET)
    row=CopyHistory(tmp_path).read(result['copy_operation_id'])
    assert row['state']=='confirmed' and row['target']==TARGET

def test_failure_not_retried_and_native_id_preserved(tmp_path):
    store=CopyHistory(tmp_path);calls=[]
    def identify(_): raise ValueError('provenance failed')
    with pytest.raises(RuntimeError,match='requires inspection'):
        store.execute(SOURCE,lambda:calls.append(1) or {'object':{'id':8}},identify)
    row=store.read(next(tmp_path.glob('*.json')).stem)
    assert calls==[1] and row['state']=='needs_attention' and row['target_actor_id']==8

def test_intent_failure_prevents_spawn(tmp_path):
    target=tmp_path/'target';target.mkdir()
    link=tmp_path/'link';link.symlink_to(target,target_is_directory=True)
    calls=[]
    with pytest.raises(ValueError):
        CopyHistory(link).execute(SOURCE,lambda:calls.append(1),lambda _:TARGET)
    assert calls==[]


def copied(store):
    return store.execute(SOURCE,lambda:{'object':{'id':8}},lambda _:TARGET)['copy_operation_id']

def test_undo_exact_target_and_persistent_double_submit_guard(tmp_path):
    store=CopyHistory(tmp_path);operation=copied(store);calls=[]
    def verify(target): assert target==TARGET
    def delete(target):
        assert store.read(operation)['undo']['state']=='attempting'
        calls.append(target)
        return {'ok':True,'actor_id':8,'backup':{'stable_id':'new-object'},'operation_id':'deletion-a'}
    store.undo(operation,verify,delete)
    assert store.read(operation)['undo']['state']=='confirmed'
    with pytest.raises(ValueError,match='eligible'):
        CopyHistory(tmp_path).undo(operation,verify,delete)
    assert calls==[TARGET]

def test_undo_failed_review_does_not_write_or_delete(tmp_path):
    store=CopyHistory(tmp_path);operation=copied(store);before=store.path(operation).read_bytes()
    def verify(_):raise ValueError('identity changed')
    with pytest.raises(ValueError,match='identity changed'):
        store.undo(operation,verify,lambda _:pytest.fail('must not delete'))
    assert store.path(operation).read_bytes()==before

def test_uncertain_deletion_is_never_retried(tmp_path):
    store=CopyHistory(tmp_path);operation=copied(store)
    def delete(_):raise RuntimeError('native disconnected')
    with pytest.raises(RuntimeError,match='requires inspection'):
        store.undo(operation,lambda _:None,delete)
    assert store.read(operation)['undo']['state']=='needs_attention'
    with pytest.raises(ValueError):store.undo(operation,lambda _:None,delete)


def test_redo_preserves_cycles_and_allows_next_undo(tmp_path):
    store=CopyHistory(tmp_path);operation=copied(store)
    selection=dict(scene_id='scene-a',version='version-a',stable_id=TARGET['stable_id'])
    def deleted(target):return dict(ok=True,actor_id=target['actor_id'],backup=selection,operation_id='delete-a')
    store.undo(operation,lambda _:None,deleted)
    new={**TARGET,'actor_id':9}
    def restore(backup):
        assert backup==selection
        assert store.read(operation)['redo']['state']=='attempting'
        return {'ok':True,'bindings':{TARGET['stable_id']:9}}
    result=store.redo(operation,'delete-a',lambda *_:None,restore,lambda *_:new)
    assert result['target']==new
    reloaded=CopyHistory(tmp_path);row=reloaded.read(operation)
    assert 'undo' not in row and 'redo' not in row
    assert row['cycles'][0]['target']==TARGET and row['cycles'][0]['undo']['state']=='confirmed'
    calls=[]
    reloaded.undo(operation,lambda target:calls.append(target),deleted)
    assert calls==[new]
    with pytest.raises(ValueError,match='cycle changed'):
        reloaded.redo(operation,'obsolete-deletion',lambda *_:None,restore,lambda *_:new)


def test_redo_unknown_result_blocks_retry_preserves_prior_undo(tmp_path):
    store=CopyHistory(tmp_path);operation=copied(store)
    selection=dict(scene_id='s',version='v',stable_id=TARGET['stable_id'])
    store.undo(operation,lambda _:None,lambda _:dict(ok=True,actor_id=8,backup=selection,operation_id='d'))
    before=store.read(operation)['undo'];calls=[]
    def restore(_):calls.append(1);raise RuntimeError('lost response')
    with pytest.raises(RuntimeError,match='requires inspection'):
        store.redo(operation,'d',lambda *_:None,restore,lambda *_:None)
    row=store.read(operation)
    assert row['undo']==before and row['redo']['state']=='needs_attention'
    with pytest.raises(ValueError):store.redo(operation,'d',lambda *_:None,restore,lambda *_:None)
    assert calls==[1]


def test_concurrent_copy_undo_deletes_once(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    store=CopyHistory(tmp_path);operation=copied(store);barrier=Barrier(2);calls=[]
    def delete(target):
        calls.append(target['actor_id'])
        return dict(ok=True,actor_id=target['actor_id'],operation_id='d',backup=dict(scene_id='s',version='v',stable_id=target['stable_id']))
    def submit():
        barrier.wait(timeout=5)
        try:store.undo(operation,lambda _:None,delete);return 'done'
        except ValueError:return 'rejected'
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:submit(),range(2)))
    assert sorted(results)==['done','rejected'] and calls==[8]

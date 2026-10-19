from concurrent.futures import ThreadPoolExecutor
from threading import Event
import pytest

from carla_safety_agent.material_history import MaterialHistory


def test_execute_waits_for_history_lock_before_native_write(tmp_path):
    history = MaterialHistory(tmp_path/'history')
    identity = dict(episode='1', object_id='2', target='house', component='mesh', slot=0)
    started, applied = Event(), Event()

    def edit():
        started.set()
        return history.execute(identity, None, 'a'*64, applied.set)

    with ThreadPoolExecutor(max_workers=1) as pool:
        with history.lock:
            future = pool.submit(edit)
            assert started.wait(2)
            assert not applied.wait(.1)
            assert not history.root.exists()
        operation = future.result(timeout=2)
    assert applied.is_set()
    assert history.read(operation)['state'] == 'confirmed'


def test_unresolved_slot_blocks_new_edit_until_explicit_recovery(tmp_path):
    history = MaterialHistory(tmp_path/'history')
    identity = dict(episode='1', object_id='2', target='house', component='mesh', slot=0)
    def failed():
        raise RuntimeError('native result unknown')
    with pytest.raises(RuntimeError):
        history.execute(identity, None, 'a'*64, failed)
    operation = next(history.root.glob('*.json')).stem
    before = history.path(operation).read_bytes()
    with pytest.raises(ValueError, match='unresolved operation') as rejected:
        history.execute(identity, None, 'b'*64, lambda: pytest.fail('must not mutate'))
    assert operation in str(rejected.value)
    assert 'Editor History' in str(rejected.value)
    assert history.path(operation).read_bytes() == before
    assert len(list(history.root.glob('*.json'))) == 1
    other = {**identity, 'slot': 1}
    history.execute(other, None, 'b'*64, lambda: None)
    row = history.read(operation)
    history.recover(operation, history.inspection_token(row), 'source', None,
                    lambda *_: None, lambda *_: None)
    new = history.execute(identity, None, 'b'*64, lambda: None)
    assert history.read(new)['state'] == 'confirmed'


def test_corrupt_history_error_identifies_file_without_mutation(tmp_path):
    history = MaterialHistory(tmp_path/'history')
    history.root.mkdir()
    bad = history.root/'broken.json'
    bad.write_text('{}')
    identity = dict(episode='1', object_id='2', target='house', component='mesh', slot=0)
    with pytest.raises(ValueError, match='broken.json cannot be verified'):
        history.execute(identity, None, 'a'*64, lambda: pytest.fail('must not apply'))
    assert bad.read_text() == '{}'
    assert list(history.root.iterdir()) == [bad]


@pytest.mark.parametrize('actor', [False, True])
def test_old_undo_cannot_bypass_another_unresolved_slot_operation(tmp_path, actor):
    from types import SimpleNamespace
    from carla_safety_agent.actor_material_history import ActorMaterialHistory, apply_with_history
    if actor:
        history = ActorMaterialHistory(tmp_path/'history')
        identity = dict(episode='1',actor_id=2,stable_id='abc',blueprint_id='vehicle.audi.a2',component='VehicleMesh',slot=4)
        def execute(before, after, callback):
            return apply_with_history(history.root, identity, before, after,
                                      SimpleNamespace(apply=callback, rollback=lambda: None))
    else:
        history = MaterialHistory(tmp_path/'history')
        identity = dict(episode='1',object_id='2',target='house',component='mesh',slot=0)
        def execute(before, after, callback):
            return history.execute(identity, before, after, callback)
    old = execute(None, 'a'*64, lambda: None)
    def failed():
        raise RuntimeError('result uncertain')
    with pytest.raises(RuntimeError):
        execute('a'*64, 'b'*64, failed)
    before = {p.name:p.read_bytes() for p in history.root.glob('*.json')}
    with pytest.raises(ValueError, match='unresolved operation'):
        history.transition(old, 'undo', old,
                           lambda *_: pytest.fail('must reject before world verification'),
                           lambda *_: pytest.fail('must not apply'))
    assert before == {p.name:p.read_bytes() for p in history.root.glob('*.json')}

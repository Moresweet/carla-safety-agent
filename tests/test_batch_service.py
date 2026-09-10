import threading
import pytest
from carla_safety_agent.batch_service import BatchService


def test_service_single_owner_cancel_and_detached_status():
    entered, release = threading.Event(), threading.Event()
    calls = []
    def step(batch):
        calls.append(batch); entered.set()
        assert release.wait(3)
        return {'action': 'started', 'execution_id': 'execution'}
    service = BatchService(step, interval=.001)
    started = service.start('batch1')
    assert entered.wait(3)
    with pytest.raises(ValueError): service.start('batch2')
    with pytest.raises(ValueError): service.cancel('batch2', started['scheduler_id'])
    snapshot = service.status(); snapshot['state'] = 'forged'
    assert service.status()['state'] == 'running'
    service.cancel('batch1', started['scheduler_id']); release.set(); service.worker.join(3)
    assert not service.worker.is_alive()
    assert service.status()['state'] == 'cancelled'
    assert service.status()['current_simulation_stopped'] is False
    assert calls == ['batch1']


def test_service_error_is_visible_and_new_start_is_explicit():
    def step(batch):
        raise OSError('lost response')
    service = BatchService(step)
    service.start('batch1'); service.worker.join(3)
    assert service.status()['state'] == 'needs_attention'
    assert service.status()['error'] == 'lost response'
    service.step = lambda batch: {'action': 'no_pending_jobs', 'states': ['completed']}
    service.start('batch1'); service.worker.join(3)
    assert service.status()['state'] == 'completed'


def test_stale_cancel_cannot_cancel_new_scheduler_for_same_batch():
    service = BatchService(lambda batch: {'action': 'paused'})
    first = service.start('batch1'); service.worker.join(3)
    entered, release = threading.Event(), threading.Event()
    def step(batch):
        entered.set(); assert release.wait(3)
        return {'action': 'paused'}
    service.step = step
    second = service.start('batch1')
    try:
        assert entered.wait(3)
        assert first['scheduler_id'] != second['scheduler_id']
        with pytest.raises(ValueError): service.cancel('batch1', first['scheduler_id'])
        assert not service.cancelled.is_set()
    finally:
        release.set(); service.worker.join(3)


@pytest.mark.parametrize('phase',['construct','start'])
def test_thread_launch_failure_is_not_a_permanent_running_scheduler(monkeypatch,phase):
    service=BatchService(lambda batch:{'action':'paused'})
    def fail(*args,**kwargs):raise RuntimeError('controlled thread allocation failure')
    with monkeypatch.context() as patch:
        if phase=='construct':patch.setattr(threading,'Thread',fail)
        else:patch.setattr(threading.Thread,'start',fail)
        with pytest.raises(RuntimeError,match='allocation failure'):service.start('batch1')
    status=service.status()
    assert status['state']=='needs_attention'
    assert status['ended_at']>=status['started_at']
    assert status['failure_phase']=='scheduler_launch'
    assert 'allocation failure' in status['error']
    assert service.worker is None
    service.start('batch1');service.worker.join(3)
    assert service.status()['state']=='paused'

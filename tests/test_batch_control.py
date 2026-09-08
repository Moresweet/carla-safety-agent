import pytest
from carla_safety_agent.batch_catalog import BatchCatalog
from carla_safety_agent.batch_control import control_batch
from carla_safety_agent.experiment_queue import ExperimentQueue


def setup(tmp_path):
    catalog = BatchCatalog(tmp_path/'batches')
    dimensions = {**{a: [{'id': 'base', 'configuration': {}}]
                     for a in ('scenes', 'models', 'weather', 'textures')}, 'seeds': [1]}
    batch_id = catalog.create(dimensions)['batch_id']
    calls = []
    def request(path, payload=None):
        calls.append((path, payload))
        return {'ready': False, 'checks': [{'id': 'test', 'ok': False}]}
    def control(action, **extra):
        return control_batch(catalog, {'batch_id': batch_id, 'action': action, **extra},
                             None, tmp_path/'scenarios', request)
    return catalog, batch_id, calls, control


def test_pause_resume_and_blocked_advance_never_launch(tmp_path):
    catalog, batch_id, calls, control = setup(tmp_path)
    assert control('pause')['dispatched'] is False
    assert control('advance')['action'] == 'paused'
    assert calls == []
    assert control('resume')['dispatched'] is False
    assert calls == []
    assert control('advance')['action'] == 'preflight_blocked'
    assert calls == [('system/preflight', None)]
    assert catalog.read(batch_id)['jobs'][0]['attempts'] == []


def test_retry_preserves_attempt_and_does_not_dispatch(tmp_path):
    catalog, batch_id, calls, control = setup(tmp_path)
    queue = ExperimentQueue(catalog.directory(batch_id))
    claim = queue.claim()
    queue.update_attempt(claim['job_id'], claim['attempt']['attempt_id'], outcome='failed',
                         result={'phase': 'prepare', 'error': 'test'})
    assert control('retry', job_id=claim['job_id'])['dispatched'] is False
    job = catalog.read(batch_id)['jobs'][0]
    assert job['state'] == 'pending' and len(job['attempts']) == 1
    assert calls == []


def test_control_rejects_invalid_fields_and_corruption_before_mutation(tmp_path):
    catalog, batch_id, calls, control = setup(tmp_path)
    for action, extra in [('delete', {}), ('pause', {'path': '/tmp'}), ('retry', {})]:
        with pytest.raises(ValueError):
            control(action, **extra)
    (catalog.directory(batch_id)/'queue.json').write_text('{}')
    with pytest.raises((ValueError, KeyError)):
        control('pause')
    assert calls == []

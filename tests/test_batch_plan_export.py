import importlib.util
from pathlib import Path
import pytest
from carla_safety_agent.batch_catalog import BatchCatalog
from carla_safety_agent.experiment_queue import ExperimentQueue


def tool(name):
    path = Path(__file__).resolve().parents[1]/'tools'/f'{name}.py'
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_export_import_preserves_plan_but_not_live_reservations(tmp_path):
    dimensions = {**{a: [{'id': 'base', 'configuration': {}}]
                     for a in ('scenes', 'models', 'weather', 'textures')}, 'seeds': [31, 32]}
    catalog = BatchCatalog(tmp_path/'original')
    batch_id = catalog.create(dimensions)['batch_id']
    queue = ExperimentQueue(catalog.directory(batch_id))
    queue.claim()
    before = queue.read()
    exported = tool('export_batch_plan').export_plan(catalog.root, batch_id, tmp_path/'transfer')
    imported = tool('create_experiment_queue').create_queue(exported['path'], tmp_path/'new-machine')
    restored = ExperimentQueue(tmp_path/'new-machine').read()
    assert restored['plan'] == before['plan']
    assert imported['plan_sha256'] == before['plan_sha256'] == exported['plan_sha256']
    assert all(j['state'] == 'pending' and j['attempts'] == [] for j in restored['jobs'])
    assert queue.read() == before
    assert exported['execution_history_included'] is False
    assert exported['assets_included'] is False
    assert exported['dispatched'] is False
    with pytest.raises(ValueError):
        tool('export_batch_plan').export_plan(catalog.root, '../escape', tmp_path/'bad')
    assert not (tmp_path/'bad').exists()

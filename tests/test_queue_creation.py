import sys
from pathlib import Path
import pytest
from carla_safety_agent.experiment_matrix import save_matrix
from carla_safety_agent.experiment_queue import ExperimentQueue
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from create_experiment_queue import create_queue


def test_verified_plan_creates_pending_queue_without_dispatch(tmp_path):
    dimensions = {**{a: [{'id': 'base', 'configuration': {}}] for a in ('scenes','models','weather','textures')}, 'seeds': [1, 2]}
    plan, digest = save_matrix(tmp_path/'plans', dimensions)
    result = create_queue(plan, tmp_path/'queue')
    assert result['plan_sha256'] == digest and result['dispatched'] is False
    assert all(j['state'] == 'pending' and not j['attempts'] for j in ExperimentQueue(tmp_path/'queue').read()['jobs'])
    assert create_queue(plan, tmp_path/'queue') == result
    plan.write_text('{}')
    with pytest.raises(ValueError): create_queue(plan, tmp_path/'other')
    assert not (tmp_path/'other').exists()

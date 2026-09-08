import sys
from pathlib import Path
import pytest
from carla_safety_agent.experiment_queue import ExperimentQueue
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from export_experiment_report import export_report


def test_report_export_does_not_overwrite_changed_archive(tmp_path):
    q = ExperimentQueue(tmp_path/'queue')
    q.create({**{a: [{'id': 'base', 'configuration': {}}] for a in ('scenes','models','weather','textures')}, 'seeds': [1]})
    path = export_report(q.root, tmp_path/'results', tmp_path/'reports')
    assert export_report(q.root, tmp_path/'results', tmp_path/'reports') == path
    path.write_text('{}')
    with pytest.raises(ValueError): export_report(q.root, tmp_path/'results', tmp_path/'reports')

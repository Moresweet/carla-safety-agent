import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace

from carla_safety_agent.carla_adapter import RuleRunCancelled


def test_owned_worker_prestart_stop_writes_stopped_result(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[1]/'tools/run_rule_scenario.py'
    spec = importlib.util.spec_from_file_location('rule_worker_test', path)
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    monkeypatch.setattr(worker.signal, 'signal', lambda *args: None)
    monkeypatch.setattr(worker, 'SessionJournal', lambda root: SimpleNamespace(
        owned_pid=lambda: os.getpid(), snapshot=lambda: {'run_id':'owned'}))
    document = {'scenario_id':'stopped-test'}
    monkeypatch.setattr(worker, 'read_verified_scenario', lambda *args: (document, 'digest'))
    monkeypatch.setattr(worker, 'scenario_from_dict', lambda doc: SimpleNamespace(**doc))
    def run(*args, **kwargs):
        assert callable(kwargs['should_stop'])
        assert callable(kwargs['on_frame'])
        raise RuleRunCancelled()
    monkeypatch.setattr(worker, 'CarlaAdapter', lambda **kwargs: SimpleNamespace(run=run))
    destination = tmp_path/'results'/'result.json'
    for name, value in {'CSA_EXECUTION_ID':'owned','SCENARIO':'plan.json',
        'CSA_SCENARIO_SHA256':'digest','CSA_EVALUATION_CONTROL_DIR':str(tmp_path/'runtime'),
        'RESULTS':str(destination),'CSA_DATASET_ROOT':str(tmp_path/'datasets')}.items():
        monkeypatch.setenv(name, value)
    worker.main()
    report = json.loads(destination.read_text())
    assert report['status'] == 'stopped' and report['elapsed_s'] == 0
    assert report['execution_id'] == 'owned' and report['scenario'] == document

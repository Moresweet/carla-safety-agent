"""Cancellation acceptance must observe inference and preserve task ownership."""
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize('outcome', ['stopped', 'completed', 'changed_owner', 'assessed_cancel', 'failed_cancel'])
def test_cancellation_requires_inference_and_matching_terminal_state(tmp_path, monkeypatch, outcome):
    tools = Path(__file__).resolve().parents[1] / 'tools'
    monkeypatch.syspath_prepend(str(tools))
    spec = importlib.util.spec_from_file_location('cancel_probe', tools / 'regression_thinktwice_native.py')
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)
    monkeypatch.setattr(probe, 'ROOT', tmp_path)
    (tmp_path / 'runs/validation').mkdir(parents=True)
    monkeypatch.setattr(sys, 'argv', ['probe', '--cancel-after-inference'])
    monkeypatch.setattr(probe.time, 'sleep', lambda _: None)
    from carla_safety_agent import world_health
    monkeypatch.setattr(world_health, 'observe_idle', lambda *a: {'sensors': 0, 'synchronous': False})
    monkeypatch.setitem(sys.modules, 'carla', SimpleNamespace(
        Client=lambda *a: SimpleNamespace(set_timeout=lambda _: None)))
    phases = iter([
        {'session': {'run_id': 'owned', 'state': 'running'},
         'progress': {'phase': 'inference', 'completed_steps': 31}},
        {'session': {'run_id': 'other' if outcome == 'changed_owner' else 'owned', 'state': 'running'},
         'progress': {'phase': 'inference', 'completed_steps': 32}},
        {'session': {'run_id': 'owned',
                     'state': 'stopped' if outcome in ('assessed_cancel', 'failed_cancel') else outcome,
                     'returncode': 0 if outcome == 'completed' else 130,
                     'outcome': {'result_assessed': outcome == 'assessed_cancel',
                                 'benchmark_failed': False,
                                 'failure_category': 'process_exit' if outcome == 'failed_cancel' else None}}},
    ])
    stops = []
    def request(route, payload=None):
        if route == 'system/preflight': return {'ready': True}
        if route == 'batches/scheduler': return {'scheduler': {'state': 'idle'}}
        if route == 'scenes/save':
            return {'document': {'objects': [], 'map': 'Town04'}, 'head': {'scene_id': 'saved'}}
        if route == 'scenario/compile': return {'scenario_path': 'path', 'scenario_sha256': 'sha'}
        if route == 'scenario/execute-plan':
            assert payload['unified_capture'] is False
            return {'execution_id': 'owned'}
        if route == 'session/status': return next(phases)
        if route == 'e2e/stop':
            assert payload == {'run_id': 'owned'}
            stops.append(payload)
            return {'state': 'stopping'}
        raise AssertionError(route)
    monkeypatch.setattr(probe, 'request', request)
    if outcome == 'stopped':
        assert probe.main() == 0
    else:
        with pytest.raises(AssertionError): probe.main()
    report = json.loads(next((tmp_path / 'runs/validation').glob('*.json')).read_text())
    assert report['ok'] is (outcome == 'stopped')
    assert len(stops) == (0 if outcome == 'changed_owner' else 1)
    if stops: assert report['stop_progress']['completed_steps'] == 32

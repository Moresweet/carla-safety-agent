import importlib.util
from pathlib import Path

import pytest


@pytest.mark.parametrize('changes,accepted', [({}, True), ({'frames': 32}, False),
    ({'frames': 79}, False), ({'frames': 81}, False), ({'valid': False}, False),
    ({'prediction_valid': False}, False),
    ({'status': 'recording'}, False), ({'status': 'saved_limit'}, False),
    ({'error': 'disk full'}, False), ({'stop_reason': 'disk_reserve'}, False)])
def test_full_run_cannot_accept_partial_or_unfinalized_capture(monkeypatch, changes, accepted):
    tools = Path(__file__).resolve().parents[1] / 'tools'
    monkeypatch.syspath_prepend(str(tools))
    spec = importlib.util.spec_from_file_location('capture_acceptance', tools / 'regression_thinktwice_native.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    data = dict(valid=True, prediction_valid=True, frames=80, status='saved', error=None, stop_reason=None)
    data.update(changes)
    assert module.complete_capture_verified([data]) is accepted
    assert not module.complete_capture_verified([])


@pytest.mark.parametrize('changes,accepted', [({}, True), ({'frames': 39}, False),
    ({'frames': 79}, True), ({'frames': 80}, False), ({'frames': 0}, False),
    ({'valid': False}, False), ({'prediction_valid': False}, False),
    ({'status': 'recording'}, False), ({'error': 'write failed'}, False),
    ({'stop_reason': 'disk_reserve'}, False)])
def test_cancelled_capture_requires_finalized_partial_inference(monkeypatch, changes, accepted):
    tools = Path(__file__).resolve().parents[1] / 'tools'
    monkeypatch.syspath_prepend(str(tools))
    spec = importlib.util.spec_from_file_location('capture_acceptance', tools / 'regression_thinktwice_native.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    data = dict(valid=True, prediction_valid=True, frames=40, status='saved', error=None, stop_reason=None)
    data.update(changes)
    assert module.cancelled_capture_verified([data]) is accepted
    assert not module.cancelled_capture_verified([])
    assert not module.cancelled_capture_verified([data, data])

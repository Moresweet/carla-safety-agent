import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize('model', ['thinktwice', 'driveadapter'])
def test_two_map_budget_rejects_before_any_service_or_world_access(monkeypatch, model):
    tools = Path(__file__).resolve().parents[1]/'tools'
    monkeypatch.syspath_prepend(str(tools))
    spec = importlib.util.spec_from_file_location('map_probe', tools/'regression_map_transition.py')
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)
    def forbidden(*args, **kwargs):
        pytest.fail('Insufficient two-map budget reached simulation')
    monkeypatch.setitem(sys.modules, 'carla', SimpleNamespace(Client=forbidden))
    monkeypatch.setattr(sys, 'argv', ['probe', '--model', model])
    monkeypatch.setattr(probe, 'request', forbidden)
    monkeypatch.setattr(probe.shutil, 'disk_usage', lambda _:SimpleNamespace(free=10*1024**3-1))
    with pytest.raises(RuntimeError, match='8 GiB capture budget'):
        probe.main()

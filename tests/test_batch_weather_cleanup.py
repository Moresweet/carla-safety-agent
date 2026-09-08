import sys
from pathlib import Path
from types import SimpleNamespace as NS
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from regression_batch_queue import restore_test_weather


@pytest.mark.parametrize('condition', ['ok', 'foreign', 'active', 'map'])
def test_weather_cleanup_requires_idle_owned_world(condition):
    writes = []
    weather = NS(precipitation=75.)
    world = NS(get_settings=lambda: NS(synchronous_mode=False),
               get_map=lambda: NS(name='Town05' if condition == 'map' else 'Town04'),
               get_weather=lambda: weather, set_weather=lambda w: writes.append(w.precipitation))
    state = {'jobs': [{'attempts': [{'attempt_id': 'a', 'execution_id': 'run'}]}]}
    session = {'state': 'running' if condition == 'active' else 'completed',
               'configuration': {'request': {'batch_attempt_id': 'other' if condition == 'foreign' else 'a'}}}
    journal = NS(read_execution=lambda _: {'configuration': {'starting_scene': {'map': 'Town04', 'weather': {'precipitation': 0.}}}})
    if condition == 'ok':
        assert restore_test_weather(state, session, journal, world)
        assert writes == [0.]
    else:
        with pytest.raises(RuntimeError): restore_test_weather(state, session, journal, world)
        assert writes == []

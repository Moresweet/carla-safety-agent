from pathlib import Path
import pytest
from carla_safety_agent.session import observed_process_identity


@pytest.mark.parametrize('error', [PermissionError, OSError, ValueError])
def test_observation_errors_are_not_absence(monkeypatch, error):
    def read(_): raise error('unavailable')
    monkeypatch.setattr(Path, 'read_text', read)
    with pytest.raises(error): observed_process_identity(123)


def test_missing_pid_and_zombie_are_absent(monkeypatch):
    def missing(_): raise FileNotFoundError()
    monkeypatch.setattr(Path, 'read_text', missing)
    assert observed_process_identity(123) is None
    text = '123 (worker (name)) ' + ' '.join(['Z'] + ['0']*18 + ['789'])
    monkeypatch.setattr(Path, 'read_text', lambda _: text)
    assert observed_process_identity(123) is None
    monkeypatch.setattr(Path, 'read_text', lambda _: text.replace(' Z ', ' S '))
    assert observed_process_identity(123) == {'pid': 123, 'start_ticks': '789'}


def test_malformed_stat_is_not_absence(monkeypatch):
    monkeypatch.setattr(Path, 'read_text', lambda _: 'truncated')
    with pytest.raises(ValueError): observed_process_identity(123)

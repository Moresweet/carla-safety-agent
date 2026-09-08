import pytest
from types import SimpleNamespace
from carla_safety_agent.experiment_queue import ExperimentQueue
from carla_safety_agent.experiment_dispatch import advance_queue


def queue(tmp_path, model):
    q = ExperimentQueue(tmp_path/'queue')
    q.create({**{a: [{'id': 'base', 'configuration': {}}]
                 for a in ('scenes', 'weather', 'textures')},
              'models': [{'id': 'model', 'configuration': model}], 'seeds': [0]})
    return q


def test_unavailable_adapter_fails_without_starting(tmp_path):
    q = queue(tmp_path, {'action': 'vad'})
    calls = []
    def request(path, data=None):
        calls.append(path); return {'ready': True}
    result = advance_queue(q, None, tmp_path/'scenarios', request)
    assert result['action'] == 'preparation_failed'
    assert calls == ['system/preflight']
    assert q.read()['jobs'][0]['state'] == 'failed'


def test_reserved_attempt_never_redispatches(tmp_path):
    q = queue(tmp_path, {'action': 'rule-run'}); q.claim()
    journal = SimpleNamespace(find_batch_attempt=lambda *args: None)
    def forbidden(*args): pytest.fail('Uncertain dispatch cannot automatically restart')
    result = advance_queue(q, journal, tmp_path/'scenarios', forbidden)
    assert result['action'] == 'recover_binding' and not result['bound']
    assert q.read()['jobs'][0]['state'] == 'reserved'


def test_busy_world_does_not_claim(tmp_path):
    q = queue(tmp_path, {'action': 'rule-run'})
    result = advance_queue(q, None, tmp_path/'scenarios', lambda _: {'ready': False})
    assert result['action'] == 'preflight_blocked'
    assert q.read()['jobs'][0]['attempts'] == []


def test_pause_persists_and_does_not_preflight_or_claim(tmp_path):
    q = queue(tmp_path, {'action': 'rule-run'})
    q.set_paused(True)
    q = ExperimentQueue(q.root)
    def forbidden(*args): pytest.fail('Paused queue must not preflight or start')
    assert advance_queue(q, None, tmp_path/'scenarios', forbidden)['action'] == 'paused'
    assert q.claim() is None
    assert q.read()['jobs'][0]['attempts'] == []
    q.set_paused(False)
    assert q.claim() is not None


def test_pause_preserves_recovery_of_current_attempt(tmp_path):
    q = queue(tmp_path, {'action': 'rule-run'}); q.claim(); q.set_paused(True)
    journal = SimpleNamespace(find_batch_attempt=lambda *args: None)
    result = advance_queue(q, journal, tmp_path/'scenarios', lambda *args: pytest.fail('No dispatch'))
    assert result['action'] == 'recover_binding'
    assert q.read()['paused'] is True

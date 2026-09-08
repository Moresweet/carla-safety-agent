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


def test_vad_batch_rejects_unrecognized_launch_options(tmp_path):
    q = queue(tmp_path, {'action': 'run', 'algorithm': 'vad', 'command': 'untrusted'})
    calls = []
    def request(path, data=None):
        calls.append(path)
        return {'ready': True}
    result = advance_queue(q, None, tmp_path/'scenarios', request)
    assert result['action'] == 'preparation_failed'
    assert calls == ['system/preflight']


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


@pytest.mark.parametrize('algorithm', ['uniad-tiny', 'vad', 'tcp'])
def test_model_dispatch_preserves_model_and_capture_request(tmp_path, monkeypatch, algorithm):
    from carla_safety_agent import experiment_dispatch
    model = {'action': 'run', 'algorithm': algorithm}
    q = queue(tmp_path, model)
    monkeypatch.setattr(experiment_dispatch, 'materialize_scenario', lambda *args: {
        'scenario_path': '/local/plan.json', 'scenario_sha256': 'sha'})
    requests = []
    def request(path, data=None):
        if path == 'system/preflight': return {'ready': True}
        requests.append(data)
        return {'execution_id': 'model-run'}
    journal = SimpleNamespace(find_batch_attempt=lambda *args: {'run_id': 'model-run'})
    assert advance_queue(q, journal, tmp_path, request)['action'] == 'started'
    assert requests[0]['action'] == 'run' and requests[0]['algorithm'] == algorithm
    assert requests[0]['unified_capture'] is True
    assert q.read()['jobs'][0]['attempts'][0]['execution_id'] == 'model-run'

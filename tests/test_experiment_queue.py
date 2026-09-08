import pytest
from carla_safety_agent.experiment_queue import ExperimentQueue


def dimensions():
    return {**{a: [{'id': 'base', 'configuration': {}}]
               for a in ('scenes', 'models', 'weather', 'textures')}, 'seeds': [0]}


def test_restart_reservation_retry_keeps_attempt_history(tmp_path):
    q = ExperimentQueue(tmp_path); q.create(dimensions())
    claim = q.claim(); job = claim['job_id']; first = claim['attempt']['attempt_id']
    resumed = ExperimentQueue(tmp_path)
    with pytest.raises(ValueError): resumed.claim()
    resumed.update_attempt(job, first, execution_id='run-1')
    with pytest.raises(ValueError): resumed.update_attempt(job, first, execution_id='wrong', outcome='completed', result={})
    resumed.update_attempt(job, first, execution_id='run-1', outcome='failed', result={'error': 'worker failed'})
    resumed.retry(job)
    second = resumed.claim()['attempt']['attempt_id']
    assert second != first
    with pytest.raises(ValueError): resumed.update_attempt(job, first, execution_id='late')
    resumed.update_attempt(job, second, execution_id='run-2')
    resumed.update_attempt(job, second, execution_id='run-2', outcome='completed', result={'report': 'new'})
    assert resumed.claim() is None
    attempts = resumed.read()['jobs'][0]['attempts']
    assert [a['state'] for a in attempts] == ['failed', 'completed']
    assert attempts[0]['result'] == {'error': 'worker failed'}
    with pytest.raises(ValueError): resumed.retry(job)


def test_create_idempotent_and_unstarted_cannot_complete(tmp_path):
    q = ExperimentQueue(tmp_path); initial = q.create(dimensions())
    assert q.create(dimensions()) == initial
    different = dimensions(); different['seeds'] = [2]
    with pytest.raises(ValueError): q.create(different)
    c = q.claim()
    with pytest.raises(ValueError): q.update_attempt(c['job_id'], c['attempt']['attempt_id'], outcome='completed', result={})
    q.update_attempt(c['job_id'], c['attempt']['attempt_id'], outcome='failed', result={'preflight': 'missing dependency'})


def test_competing_queue_clients_cannot_reserve_twice(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    ExperimentQueue(tmp_path).create(dimensions())
    def claim():
        try:
            return ExperimentQueue(tmp_path).claim()
        except ValueError:
            return None
    with ThreadPoolExecutor(max_workers=4) as pool:
        claims = list(pool.map(lambda _: claim(), range(4)))
    assert sum(c is not None for c in claims) == 1
    assert len(ExperimentQueue(tmp_path).read()['jobs'][0]['attempts']) == 1


@pytest.mark.parametrize('status,live,expected', [('running', False, False),
    ('recovering', False, False), ('completed', True, False), ('completed', False, True),
    ('failed', False, True), ('stopped', False, True)])
def test_reconcile_requires_terminal_session_and_dead_process(tmp_path, monkeypatch, status, live, expected):
    from types import SimpleNamespace
    from carla_safety_agent import session
    identity = {'pid': 123, 'start_ticks': '456'}
    monkeypatch.setattr(session, 'observed_process_identity', lambda pid: identity if live else None)
    q = ExperimentQueue(tmp_path); q.create(dimensions()); c = q.claim()
    job, attempt = c['job_id'], c['attempt']['attempt_id']
    q.update_attempt(job, attempt, execution_id='run')
    record = {'run_id': 'run', 'state': status, 'process': identity, 'ended_at': 12,
              'returncode': 0, 'error': None, 'outcome': {'benchmark_failed': True}}
    journal = SimpleNamespace(read_execution=lambda run: record)
    result = q.reconcile(job, attempt, journal)
    assert result['reconciled'] is expected
    saved = q.read()['jobs'][0]
    assert saved['state'] == (status if expected else 'running')
    if expected:
        assert saved['attempts'][0]['result']['benchmark_passed'] is False


def test_reconcile_observation_failure_retains_running_attempt(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from carla_safety_agent import session
    def denied(pid):
        raise PermissionError('Cannot inspect process')
    monkeypatch.setattr(session, 'observed_process_identity', denied)
    q = ExperimentQueue(tmp_path); q.create(dimensions()); c = q.claim()
    job, attempt = c['job_id'], c['attempt']['attempt_id']
    q.update_attempt(job, attempt, execution_id='run')
    journal = SimpleNamespace(read_execution=lambda _: {'run_id': 'run', 'state': 'completed',
        'process': {'pid': 123, 'start_ticks': '4'}, 'ended_at': 1, 'returncode': 0})
    with pytest.raises(PermissionError): q.reconcile(job, attempt, journal)
    assert q.read()['jobs'][0]['state'] == 'running'
    with pytest.raises(ValueError): q.claim()

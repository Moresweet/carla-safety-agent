import pytest
from carla_safety_agent.experiment_queue import ExperimentQueue
from carla_safety_agent.experiment_report import summarize_queue


def test_report_does_not_infer_success_from_completion(tmp_path):
    q = ExperimentQueue(tmp_path)
    q.create({**{a: [{'id': 'base', 'configuration': {}}] for a in ('scenes','models','weather','textures')}, 'seeds': [1]})
    c = q.claim(); job, attempt = c['job_id'], c['attempt']['attempt_id']
    q.update_attempt(job, attempt, execution_id='run')
    q.update_attempt(job, attempt, execution_id='run', outcome='completed', result={})
    report = summarize_queue(q.read())
    assert report['all_executions_completed'] is True
    assert report['rows'][0]['benchmark_passed'] is None
    assert report['rows'][0]['data_quality_verified'] is None
    bad = q.read(); bad['plan']['dimensions']['seeds'] = [2]
    with pytest.raises(ValueError): summarize_queue(bad)


def test_pending_retry_does_not_inherit_old_failure(tmp_path):
    q = ExperimentQueue(tmp_path)
    q.create({**{a: [{'id': 'base', 'configuration': {}}] for a in ('scenes','models','weather','textures')}, 'seeds': [1]})
    c = q.claim(); q.update_attempt(c['job_id'], c['attempt']['attempt_id'], outcome='failed', result={'error': 'prepare'})
    assert summarize_queue(q.read())['rows'][0]['error'] == 'prepare'
    q.retry(c['job_id'])
    row = summarize_queue(q.read())['rows'][0]
    assert row['error'] is None and row['attempt_count'] == 1
    assert row['execution_state'] == 'pending'

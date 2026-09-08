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


@pytest.mark.parametrize('defect', [None, 'execution', 'scenario', 'metric', 'outside'])
def test_verified_metrics_identity_and_values(tmp_path, defect):
    import json
    import hashlib
    from carla_safety_agent.experiment_matrix import canonical
    from carla_safety_agent.experiment_report import verified_rule_metrics
    scenario = {'seed': 1}
    digest = hashlib.sha256(canonical(scenario)).hexdigest()
    path = tmp_path/'result.json'
    result = {'execution_id': 'run', 'scenario_sha256': digest, 'scenario': scenario,
        'status': 'passed', 'collision': False, 'min_ttc_s': None, 'min_distance_m': None,
        'elapsed_s': 1, 'risk_score': 0, 'failure_reasons': []}
    execution = {'run_id': 'run', 'kind': 'rule-run', 'state': 'completed',
                 'configuration': {'results': str(path), 'scenario_sha256': digest}}
    if defect == 'execution': result['execution_id'] = 'other'
    if defect == 'scenario': result['scenario']['seed'] = 2
    if defect == 'metric': result['risk_score'] = True
    path.write_text(json.dumps(result))
    root = tmp_path/'different' if defect == 'outside' else tmp_path
    if defect:
        with pytest.raises(ValueError): verified_rule_metrics(execution, root)
    else:
        metrics = verified_rule_metrics(execution, root)
        assert metrics['benchmark_passed'] is True and metrics['min_ttc_s'] is None

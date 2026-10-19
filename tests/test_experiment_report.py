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


@pytest.mark.parametrize('contents', ['[]', '{"execution_id":"a","execution_id":"b"}'])
def test_bad_result_preserves_queue_report_but_excludes_metrics(tmp_path, contents):
    q=ExperimentQueue(tmp_path/'queue')
    q.create({**{a:[{'id':'base','configuration':{}}] for a in ('scenes','models','weather','textures')},'seeds':[1]})
    claim=q.claim();job=claim['job_id'];attempt=claim['attempt']['attempt_id']
    q.update_attempt(job,attempt,execution_id='run')
    results=tmp_path/'results';results.mkdir()
    path=results/'result.json';path.write_text(contents)
    execution={'run_id':'run','kind':'rule-run','state':'completed',
        'configuration':{'results':str(path),'scenario_sha256':'a'*64,
            'request':{'batch_job_id':job,'batch_attempt_id':attempt}}}
    q.update_attempt(job,attempt,execution_id='run',outcome='completed',
        result={'source':'session_journal','execution':execution,'benchmark_passed':True})
    before=q.read()
    report=summarize_queue(before,results)
    row=report['rows'][0]
    assert report['all_executions_completed'] is True
    assert row['metrics_error']
    assert 'metrics' not in row and row['benchmark_passed'] is None
    assert q.read()==before and path.read_text()==contents


def test_pending_retry_does_not_inherit_old_failure(tmp_path):
    q = ExperimentQueue(tmp_path)
    q.create({**{a: [{'id': 'base', 'configuration': {}}] for a in ('scenes','models','weather','textures')}, 'seeds': [1]})
    c = q.claim(); q.update_attempt(c['job_id'], c['attempt']['attempt_id'], outcome='failed', result={'error': 'prepare'})
    assert summarize_queue(q.read())['rows'][0]['error'] == 'prepare'
    q.retry(c['job_id'])
    row = summarize_queue(q.read())['rows'][0]
    assert row['error'] is None and row['attempt_count'] == 1
    assert row['execution_state'] == 'pending'
    assert row['attempts'][0]['state']=='failed'
    assert row['attempts'][0]['error']=='prepare'
    assert row['attempts'][0]['execution_id'] is None


def test_retry_history_remains_visible_without_mutable_ledger_references(tmp_path):
    q=ExperimentQueue(tmp_path)
    q.create({**{a:[{'id':'base','configuration':{}}] for a in ('scenes','models','weather','textures')},'seeds':[1]})
    first=q.claim();job=first['job_id'];aid=first['attempt']['attempt_id']
    q.update_attempt(job,aid,execution_id='run1')
    q.update_attempt(job,aid,execution_id='run1',outcome='stopped',result={'phase':'execution','error':'x'*2100})
    q.retry(job);second=q.claim()['attempt']['attempt_id'];q.update_attempt(job,second,execution_id='run2')
    q.update_attempt(job,second,execution_id='run2',outcome='completed',result={})
    state=q.read();history=summarize_queue(state)['rows'][0]['attempts']
    assert [a['execution_id'] for a in history]==['run1','run2']
    assert [a['state'] for a in history]==['stopped','completed']
    assert len(history[0]['error'])==2000 and history[0]['error_truncated']
    assert history[1]['error'] is None and history[0]['phase']=='execution'
    history[0]['state']='forged'
    assert state['jobs'][0]['attempts'][0]['state']=='stopped'


@pytest.mark.parametrize('wrong', ['job', 'attempt'])
def test_valid_execution_cannot_be_assigned_to_wrong_queue_job(tmp_path, wrong):
    q = ExperimentQueue(tmp_path)
    q.create({**{a: [{'id': 'base', 'configuration': {}}] for a in ('scenes','models','weather','textures')}, 'seeds': [1]})
    c = q.claim(); job, attempt = c['job_id'], c['attempt']['attempt_id']
    q.update_attempt(job, attempt, execution_id='run')
    request = {'batch_job_id': 'other' if wrong == 'job' else job,
               'batch_attempt_id': 'other' if wrong == 'attempt' else attempt}
    with pytest.raises(ValueError, match='another batch'):
        q.update_attempt(job, attempt, execution_id='run', outcome='completed', result={
            'source': 'session_journal', 'execution': {'run_id': 'run', 'configuration': {'request': request}}})
    assert q.read()['jobs'][0]['state']=='running'


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


def test_native_model_nested_results_require_matching_scenario(tmp_path):
    import json
    import hashlib
    from carla_safety_agent.experiment_matrix import canonical
    from carla_safety_agent.experiment_report import verified_rule_metrics
    scenario = {'scenario_id': 'scenario'}
    digest = hashlib.sha256(canonical(scenario)).hexdigest()
    path = tmp_path/'model.json'
    payload = {'schema_version': 'carla-safety-evaluation/0.1', 'execution_id': 'run',
        'scenario_sha256': digest, 'scenario': scenario, 'result': {'scenario_id': 'scenario',
        'status': 'passed', 'collision': False, 'min_ttc_s': None, 'min_distance_m': 20,
        'elapsed_s': 1, 'risk_score': 0, 'failure_reasons': []}}
    execution = {'run_id': 'run', 'kind': 'run', 'state': 'completed',
        'configuration': {'results': str(path), 'scenario_sha256': digest}}
    path.write_text(json.dumps(payload))
    assert verified_rule_metrics(execution, tmp_path)['benchmark_passed'] is True
    payload['result']['scenario_id'] = 'other'
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match='Nested'): verified_rule_metrics(execution, tmp_path)

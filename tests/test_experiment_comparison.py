import copy
import pytest
from carla_safety_agent.experiment_report import compare_variants


def rows():
    return [{'job_id': variant, 'variants': {'scenes': 's', 'models': 'm', 'weather': 'w', 'textures': variant},
             'seed': 1, 'execution_state': 'completed', 'metrics': {'min_ttc_s': None,
                 'min_distance_m': distance, 'risk_score': 2, 'elapsed_s': 10, 'collision': False}}
            for variant, distance in [('original', 5), ('edited', 3)]]


def test_matched_difference_preserves_missing_metric():
    result = compare_variants({'rows': rows()}, 'textures', 'original', 'edited')
    assert result['comparable_count'] == 1
    assert result['pairs'][0]['candidate_minus_baseline']['min_distance_m'] == -2
    assert result['pairs'][0]['candidate_minus_baseline']['min_ttc_s'] is None


@pytest.mark.parametrize('change', ['seed', 'duration', 'failed', 'stopped', 'missing'])
def test_unmatched_or_incomplete_results_are_not_compared(change):
    data = rows()
    if change == 'seed': data[1]['seed'] = 2
    if change == 'duration': data[1]['metrics']['elapsed_s'] = 1
    if change == 'failed': data[1]['execution_state'] = 'failed'
    if change == 'stopped': data[1]['execution_state'] = 'stopped'
    if change == 'missing': data.pop()
    result = compare_variants({'rows': data}, 'textures', 'original', 'edited')
    assert result['comparable_count'] == 0
    assert all('reason' in p for p in result['pairs'])
    assert result['excluded_count']==len(result['pairs'])
    assert sum(result['exclusion_counts'].values())==result['excluded_count']
    if change in ('failed','stopped'):
        assert result['execution_state_counts']['edited']=={change:1}


def test_duplicate_pair_rejected():
    data = rows(); data.append(copy.deepcopy(data[0]))
    with pytest.raises(ValueError): compare_variants({'rows': data}, 'textures', 'original', 'edited')


@pytest.mark.parametrize('content', ['[]', 'null', '{"execution_id":"a","execution_id":"b"}', '{"x":NaN}'])
def test_ambiguous_or_non_object_result_rejected(tmp_path, content):
    from carla_safety_agent.experiment_report import verified_rule_metrics
    path=tmp_path/'result.json';path.write_text(content)
    execution={'kind':'rule-run','state':'completed','run_id':'a',
               'configuration':{'results':str(path),'scenario_sha256':'a'*64}}
    with pytest.raises(ValueError):
        verified_rule_metrics(execution,tmp_path)


def test_special_result_file_is_rejected_without_waiting_for_writer(tmp_path):
    import os
    from carla_safety_agent.experiment_report import verified_rule_metrics
    path=tmp_path/'result.json';os.mkfifo(path)
    execution={'kind':'rule-run','state':'completed','run_id':'a',
               'configuration':{'results':str(path),'scenario_sha256':'a'*64}}
    with pytest.raises(ValueError,match='file type'):
        verified_rule_metrics(execution,tmp_path)

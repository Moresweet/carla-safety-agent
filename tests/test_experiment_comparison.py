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


@pytest.mark.parametrize('change', ['seed', 'duration', 'failed', 'missing'])
def test_unmatched_or_incomplete_results_are_not_compared(change):
    data = rows()
    if change == 'seed': data[1]['seed'] = 2
    if change == 'duration': data[1]['metrics']['elapsed_s'] = 1
    if change == 'failed': data[1]['execution_state'] = 'failed'
    if change == 'missing': data.pop()
    result = compare_variants({'rows': data}, 'textures', 'original', 'edited')
    assert result['comparable_count'] == 0
    assert all('reason' in p for p in result['pairs'])


def test_duplicate_pair_rejected():
    data = rows(); data.append(copy.deepcopy(data[0]))
    with pytest.raises(ValueError): compare_variants({'rows': data}, 'textures', 'original', 'edited')

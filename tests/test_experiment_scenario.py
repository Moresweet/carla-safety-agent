import hashlib
import pytest
from carla_safety_agent.experiment_matrix import canonical, compile_matrix
from carla_safety_agent.experiment_scenario import materialize_scenario
from carla_safety_agent.natural_language import NaturalLanguageCompiler
from carla_safety_agent.scenario_archive import read_verified_scenario


def matrix():
    scenario = NaturalLanguageCompiler().compile('Town04 前车急刹').scenario.to_dict()
    variant = lambda identity, config: {'id': identity, 'configuration': config}
    return {'scenes': [variant('base', {'scenario': scenario,
        'scenario_sha256': hashlib.sha256(canonical(scenario)).hexdigest()})],
        'models': [variant('rule', {'action': 'rule-run'})],
        'textures': [variant('original', {})],
        'weather': [variant('rain', {'precipitation': 75})], 'seeds': [1, 2]}


def test_materialized_axes_change_actual_scenario(tmp_path):
    dimensions = matrix(); plan = compile_matrix(dimensions)
    outputs = [materialize_scenario(tmp_path, job) for job in plan['jobs']]
    assert outputs[0]['scenario_path'] != outputs[1]['scenario_path']
    for seed, output in zip([1, 2], outputs):
        scenario, _ = read_verified_scenario(output['scenario_path'], output['scenario_sha256'])
        assert scenario['seed'] == seed and scenario['environment']['precipitation'] == 75
        assert output['execution_ready'] is False
    assert dimensions['scenes'][0]['configuration']['scenario']['environment']['precipitation'] == 0


def test_rejects_source_tampering_and_unsupported_weather(tmp_path):
    d = matrix(); d['scenes'][0]['configuration']['scenario']['seed'] = 100
    with pytest.raises(ValueError, match='checksum'): materialize_scenario(tmp_path, compile_matrix(d)['jobs'][0])
    d = matrix(); d['weather'][0]['configuration'] = {'friction_scale': .5}
    with pytest.raises(ValueError, match='Unsupported'): materialize_scenario(tmp_path, compile_matrix(d)['jobs'][0])
    assert not list(tmp_path.iterdir())


def test_texture_variant_is_bound_into_verified_scenario(tmp_path):
    d = matrix()
    textures = {'environment_materials': [{'target':'house', 'component':'mesh', 'slot':0, 'texture':'a'*64}]}
    d['textures'][0]['configuration'] = textures
    output = materialize_scenario(tmp_path, compile_matrix(d)['jobs'][0])
    saved, _ = read_verified_scenario(output['scenario_path'], output['scenario_sha256'])
    assert saved['provenance']['experiment_matrix']['texture_configuration'] == textures

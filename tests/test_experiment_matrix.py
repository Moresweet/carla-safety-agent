import copy
import json
import pytest
from carla_safety_agent.experiment_matrix import compile_matrix, save_matrix


def dimensions():
    return {**{axis: [{'id': 'original', 'configuration': {}}]
               for axis in ('scenes', 'models', 'weather', 'textures')}, 'seeds': [0, 1]}


def test_matrix_expansion_identity_and_immutable_archive(tmp_path):
    d = dimensions()
    d['models'].append({'id': 'vad', 'configuration': {'checkpoint_sha256': 'example'}})
    plan = compile_matrix(d)
    assert plan['job_count'] == 4
    assert len({j['job_id'] for j in plan['jobs']}) == 4
    assert plan['execution_status'] == 'not_started'
    path, digest = save_matrix(tmp_path, d)
    assert save_matrix(tmp_path, copy.deepcopy(d)) == (path, digest)
    d['models'][0]['configuration']['changed'] = True
    assert 'changed' not in plan['jobs'][0]['configuration']['models']['configuration']
    changed, _ = save_matrix(tmp_path, d)
    assert changed != path and json.loads(path.read_text()) == plan
    path.write_text('{}')
    with pytest.raises(ValueError): save_matrix(tmp_path, plan['dimensions'])


@pytest.mark.parametrize('axis,value', [('seeds', [True]), ('seeds', [0, 0]),
    ('seeds', list(range(257))), ('models', []), ('weather', [{'id': '../x', 'configuration': {}}]),
    ('textures', [{'id': 'bad', 'configuration': {'x': float('nan')}}])])
def test_matrix_rejects_invalid_or_unbounded_dimensions(axis, value):
    d = dimensions(); d[axis] = value
    with pytest.raises(ValueError): compile_matrix(d)

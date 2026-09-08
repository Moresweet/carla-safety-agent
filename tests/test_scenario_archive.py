import pytest
from carla_safety_agent.scenario_archive import archive_scenario


def test_content_identity_preserves_different_options(tmp_path):
    first = {'scenario_id':'same','oracle':{'max_duration_s':10}}
    path, digest = archive_scenario(tmp_path,first)
    assert archive_scenario(tmp_path,dict(reversed(list(first.items())))) == (path,digest)
    other, changed = archive_scenario(tmp_path,{**first,'oracle':{'max_duration_s':20}})
    assert path != other and digest != changed and path.is_file() and other.is_file()
    path.write_text('corrupt')
    with pytest.raises(ValueError,match='differs'): archive_scenario(tmp_path,first)
    assert path.read_text()=='corrupt'


def test_archive_rejects_nonfinite_and_symlink(tmp_path):
    with pytest.raises(ValueError): archive_scenario(tmp_path,{'speed':float('nan')})
    payload={'scenario_id':'test'}
    path,_=archive_scenario(tmp_path,payload)
    target=tmp_path/'target'
    path.rename(target)
    path.symlink_to(target)
    with pytest.raises(ValueError): archive_scenario(tmp_path,payload)

import pytest
from carla_safety_agent.material_library import MaterialLibrary, exact_environment_target


def test_exact_identity_only():
    assert exact_environment_target('House_1_SM_0', {'House_1','House_10'}) == 'House_1'
    with pytest.raises(ValueError): exact_environment_target('House_1', {'House_10'})
    with pytest.raises(ValueError): exact_environment_target('House_1_SM', {'House_1','House_1_SM'})


def test_texture_checksum_and_episode_history(tmp_path):
    library=MaterialLibrary(tmp_path)
    digest=library.put_texture(b'test texture bytes')
    assert library.texture(digest)==b'test texture bytes'
    library.record(1,'house','mesh',0,digest)
    assert len(MaterialLibrary(tmp_path).overrides(1))==1
    assert not library.overrides(2)
    library.record(1,'house','mesh',0,None)
    assert not library.overrides(1)
    with pytest.raises(ValueError): library.texture('../secret')

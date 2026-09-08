import pytest
from carla_safety_agent.scene_store import validate_transform_patch


@pytest.mark.parametrize('patch',[None,{'scale':1},{'location':None},{'rotation':{'x':2}},
                                 {'location':{'x':True}},{'location':{'x':'2'}},
                                 {'location':{'x':float('nan')}},{'rotation':{'yaw':float('inf')}}])
def test_invalid_patch(patch):
    with pytest.raises(ValueError): validate_transform_patch(patch)


def test_partial_patch_preserves_omitted_components():
    patch={'location':{'x':2},'rotation':{'yaw':-45.5}}
    validate_transform_patch(patch)
    assert patch=={'location':{'x':2},'rotation':{'yaw':-45.5}}
    validate_transform_patch({})

import pytest
from carla_safety_agent.input_archive import validate_input_coverage


def test_speed_dict_and_camera_array_jointly_cover_inputs():
    validate_input_coverage(['SPEED', 'CAM_FRONT'], ['CAM_FRONT'], {'SPEED': {'speed': 11.758416349652581}})


@pytest.mark.parametrize('structured', [{}, {'SPEED': {}}, {'SPEED': {'speed': None}},
    {'SPEED': {'speed': float('nan')}}, {'SPEED': {'speed': 1}, 'EXTRA': {'x': 1}}])
def test_missing_or_corrupt_structured_input_rejected(structured):
    with pytest.raises(ValueError):
        validate_input_coverage(['SPEED', 'CAM_FRONT'], ['CAM_FRONT'], structured)


def test_duplicate_array_and_structure_rejected():
    with pytest.raises(ValueError):
        validate_input_coverage(['SPEED'], ['SPEED'], {'SPEED': {'speed': 1}})

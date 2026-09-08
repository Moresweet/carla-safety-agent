import json
import pytest
from carla_safety_agent.material_mesh import validate_preview


@pytest.mark.parametrize('count,vertices', [(True,[0]*15), (0,[]), (1,[0]*14),
                                           (1,[float('nan')]*15), (1,[True]*15)])
def test_invalid_preview_rejected(count, vertices):
    with pytest.raises(ValueError):
        validate_preview(json.dumps({'triangleCount':count,'vertices':vertices}).encode())


def test_repeating_uvs_are_valid():
    vertices = [0,0,0,-2,4]*3
    assert validate_preview(json.dumps({'triangleCount':1,'vertices':vertices}).encode())['vertices'] == vertices

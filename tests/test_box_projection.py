import itertools
import numpy as np
import pytest
from carla_safety_agent.projection import project_box
from carla_safety_agent.sensor_capture import calibration


def camera():
    return calibration(dict(type='sensor.camera.rgb', width=640, height=360,
                            fov=90, x=0, y=0, z=0))


def vertices(center):
    return np.array(list(itertools.product((-1, 1), repeat=3)))+center


def test_front_box_has_twelve_edges_and_known_corner():
    result = project_box(vertices([10, 0, 0]), np.eye(4), camera())
    assert len(result) == 12
    assert result[0][:2] == pytest.approx([320-320/9, 180+320/9])


def test_behind_box_is_empty_and_near_plane_crossing_is_clipped():
    assert project_box(vertices([-10, 0, 0]), np.eye(4), camera()) == []
    result = np.array(project_box(vertices([1, 0, 0]), np.eye(4), camera()))
    assert len(result) > 0 and np.isfinite(result).all()
    assert ((result[:, [0, 2]] >= 0) & (result[:, [0, 2]] <= 639)).all()
    assert ((result[:, [1, 3]] >= 0) & (result[:, [1, 3]] <= 359)).all()


def test_world_to_ego_translation_and_invalid_geometry():
    inverse = np.eye(4); inverse[0, 3] = -100
    assert np.array(project_box(vertices([110, 0, 0]), inverse, camera())) == pytest.approx(
        np.array(project_box(vertices([10, 0, 0]), np.eye(4), camera())))
    with pytest.raises(ValueError):
        project_box(np.zeros((7, 3)), inverse, camera())

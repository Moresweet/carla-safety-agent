from types import SimpleNamespace as NS

from carla_safety_agent.sensor_capture import actor_ground_truth


def test_capture_preserves_native_box_pose_and_vertices():
    transform = NS(get_matrix=lambda: [[1, 0, 0, 20], [0, 1, 0, 30],
                                      [0, 0, 1, 0], [0, 0, 0, 1]])
    vertices = [NS(x=i, y=i+1, z=i+2) for i in range(8)]
    calls = []
    box = NS(location=NS(x=1, y=2, z=3), extent=NS(x=4, y=5, z=6),
             rotation=NS(pitch=10, yaw=20, roll=30),
             get_world_vertices=lambda pose: calls.append(pose) or vertices)
    actor = NS(id=7, type_id='static.prop.test', bounding_box=box,
               get_transform=lambda: transform)
    result = actor_ground_truth(actor)
    assert calls == [transform]
    assert result['bounding_box']['location'] == {'x': 1, 'y': 2, 'z': 3}
    assert result['bounding_box']['rotation'] == {'pitch': 10, 'yaw': 20, 'roll': 30}
    assert result['bounding_box']['world_vertices'][7] == {'x': 7, 'y': 8, 'z': 9}
    assert result['extent'] == result['bounding_box']['extent']

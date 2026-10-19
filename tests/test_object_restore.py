import copy
import pytest
from carla_safety_agent.object_restore import object_restore_document


def scene():
    pose = {'location': dict(x=1, y=2, z=3), 'rotation': dict(pitch=0, yaw=0, roll=0)}
    return {'map': 'Town04', 'objects': [
        {'stable_id': key, 'blueprint_id': 'vehicle.audi.a2', 'transform': copy.deepcopy(pose)}
        for key in ('target', 'other')],
        'actor_materials': [{'stable_id': key, 'blueprint_id': 'vehicle.audi.a2',
                            'component': 'VehicleMesh', 'slot': 4, 'texture': 'a'*64}
                           for key in ('target', 'other')],
        'weather': {'wetness': 80}, 'spectator': pose,
        'environment_materials': [], 'hidden_environment': []}


def test_select_only_target_and_material_without_mutating_snapshot():
    original = scene()
    unchanged = copy.deepcopy(original)
    selected = object_restore_document(original, 'target')
    assert set(selected) == {'schema_version', 'map', 'objects', 'actor_materials'}
    assert selected['objects'] == original['objects'][:1]
    assert selected['actor_materials'] == original['actor_materials'][:1]
    selected['objects'][0]['transform']['location']['x'] = 99
    assert original == unchanged


@pytest.mark.parametrize('key', ['missing', '../bad', None])
def test_missing_or_invalid_selection_rejected(key):
    with pytest.raises(ValueError):
        object_restore_document(scene(), key)

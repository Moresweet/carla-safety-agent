from types import SimpleNamespace as NS
import pytest
from carla_safety_agent.world_readiness import require_idle_native_world, map_matches


def test_existing_synchronous_owner_blocks_without_actor_query():
    world=NS(get_settings=lambda:NS(synchronous_mode=True),
        get_actors=lambda:pytest.fail('Do not query another synchronous owner'))
    with pytest.raises(ValueError,match='synchronous owner'): require_idle_native_world(world)


def test_existing_sensors_are_preserved_and_reported():
    sensor=NS(id=123,destroy=lambda:pytest.fail('Never delete another task sensor'))
    world=NS(get_settings=lambda:NS(synchronous_mode=False),get_actors=lambda:NS(filter=lambda _:[sensor]))
    with pytest.raises(ValueError,match='IDs: 123'): require_idle_native_world(world)


def test_idle_world_is_allowed():
    world=NS(get_settings=lambda:NS(synchronous_mode=False),get_actors=lambda:NS(filter=lambda _:[]))
    require_idle_native_world(world)


@pytest.mark.parametrize('requested,current,expected', [
    ('Town04','Carla/Maps/Town04',True),
    ('town04','/Game/Carla/Maps/Town04',True),
    ('Town04','Carla/Maps/Town04_Opt',False),
    ('Town04','Carla/Maps/Town040',False),
    ('/Game/Carla/Maps/Town04','Carla/Maps/Town04',True),
    ('/Game/Custom/Town04','Carla/Maps/Town04',False),
])
def test_map_identity_is_not_substring_match(requested,current,expected):
    assert map_matches(requested,current) is expected

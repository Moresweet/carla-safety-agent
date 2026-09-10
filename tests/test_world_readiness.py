from types import SimpleNamespace as NS
import pytest
from carla_safety_agent.world_readiness import require_idle_native_world


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

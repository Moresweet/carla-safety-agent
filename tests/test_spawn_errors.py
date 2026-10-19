from types import SimpleNamespace
import pytest
from carla_safety_agent.spawn_errors import SpawnCollision, spawn_native


@pytest.mark.parametrize('message',[
    'RPC timeout', 'collision metadata write failed',
    'Editor spawn failed: collision; cleanup unconfirmed for actor 7',
])
def test_ambiguous_or_post_creation_errors_are_not_retryable(message):
    error=RuntimeError(message)
    def fail(*_):raise error
    with pytest.raises(RuntimeError) as caught:
        spawn_native(SimpleNamespace(spawn_actor=fail),None,None)
    assert caught.value is error and not isinstance(caught.value,SpawnCollision)


def test_exact_native_collision_is_classified():
    def fail(*_):raise RuntimeError('Spawn failed because of collision at spawn position')
    with pytest.raises(SpawnCollision):spawn_native(SimpleNamespace(spawn_actor=fail),None,None)


def test_successful_native_actor_returned_unchanged():
    actor=object()
    assert spawn_native(SimpleNamespace(spawn_actor=lambda *_:actor),None,None) is actor

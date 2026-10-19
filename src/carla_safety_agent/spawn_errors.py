"""Retry classification only at the native spawn boundary, never after creation."""


class SpawnCollision(RuntimeError):
    """Server explicitly rejected creation due to occupied spawn position."""


def spawn_native(world, blueprint, transform):
    try:
        return world.spawn_actor(blueprint, transform)
    except RuntimeError as error:
        # Verified against this CARLA tree's ActorSpawnResult.cpp. Unknown errors,
        # including RPC timeouts with ambiguous creation outcomes, never retry.
        if str(error).strip() == 'Spawn failed because of collision at spawn position':
            raise SpawnCollision(str(error)) from error
        raise

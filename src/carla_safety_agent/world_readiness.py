"""Read-only exclusive-owner gate. Never deletes another tool's sensors."""


def require_idle_native_world(world):
    if world.get_settings().synchronous_mode:
        raise ValueError('Another synchronous owner is active; stop it before evaluation')
    sensors = list(world.get_actors().filter('sensor.*'))
    if sensors:
        identities = ', '.join(str(sensor.id) for sensor in sensors[:10])
        raise ValueError(f'Live sensors prevent exclusive evaluation ({len(sensors)}; IDs: {identities}). '
                           'Stop their owning task or recover it; no sensors were deleted')

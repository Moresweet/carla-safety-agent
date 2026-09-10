"""Read-only exclusive-owner gate. Never deletes another tool's sensors."""


def map_matches(requested, current):
    """Short CARLA map names match exactly, not Town04 prefixes such as _Opt."""
    def normalize(value):
        if not isinstance(value, str) or not value.strip('/'):
            raise ValueError('Map name must be nonempty')
        value = value.strip('/').casefold()
        return value[5:] if value.startswith('game/') else value
    wanted, actual = normalize(requested), normalize(current)
    return wanted == (actual if '/' in wanted else actual.rsplit('/', 1)[-1])


def require_idle_native_world(world):
    if world.get_settings().synchronous_mode:
        raise ValueError('Another synchronous owner is active; stop it before evaluation')
    sensors = list(world.get_actors().filter('sensor.*'))
    if sensors:
        identities = ', '.join(str(sensor.id) for sensor in sensors[:10])
        raise ValueError(f'Live sensors prevent exclusive evaluation ({len(sensors)}; IDs: {identities}). '
                           'Stop their owning task or recover it; no sensors were deleted')

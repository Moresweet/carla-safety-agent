"""Destroy only owned sensors without trusting a lagging client snapshot."""


def destroy_owned_sensors(sensors, *, client=None, carla=None):
    sensors = list(sensors)
    if not sensors:
        return [], []
    if client is None:
        remaining, errors = [], []
        for sensor in sensors:
            try:
                if sensor.destroy() is False:
                    raise RuntimeError('destroy returned false')
            except Exception as exc:
                remaining.append(sensor)
                errors.append(f'Sensor destroy: {exc}')
        return remaining, errors
    try:
        ids = [sensor.id for sensor in sensors]
        if any(type(actor_id) is not int or actor_id <= 0 for actor_id in ids):
            raise ValueError('Invalid owned sensor ID')
        unique = list(dict.fromkeys(ids))
        # False is do_tick: cleanup must not advance somebody else's world.
        responses = client.apply_batch_sync(
            [carla.command.DestroyActor(actor_id) for actor_id in unique], False)
        if len(responses) != len(unique):
            raise RuntimeError('Incomplete sensor destruction acknowledgement')
        failures = {actor_id: response.error for actor_id, response in zip(unique, responses)
                    if response.error}
        return ([sensor for sensor in sensors if sensor.id in failures],
                [f'Sensor {actor_id} destroy: {error}' for actor_id, error in failures.items()])
    except Exception as exc:
        # A timeout is not proof of destruction. Keep ownership for diagnosis/retry.
        return sensors, [f'Owned sensor destruction unconfirmed: {exc}']

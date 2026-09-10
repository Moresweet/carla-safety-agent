from types import SimpleNamespace as NS

import pytest

from carla_safety_agent.owned_sensors import destroy_owned_sensors


def test_stale_snapshot_does_not_skip_owned_ids_or_tick():
    calls = []
    sensor = NS(id=42, is_alive=False)
    client = NS(apply_batch_sync=lambda commands, tick: calls.append((commands, tick)) or [NS(error='')])
    carla = NS(command=NS(DestroyActor=lambda actor_id: ('destroy', actor_id)))
    assert destroy_owned_sensors([sensor, sensor], client=client, carla=carla) == ([], [])
    assert calls == [([('destroy', 42)], False)]


@pytest.mark.parametrize('response', [[], [NS(error='not found')]])
def test_unconfirmed_destruction_retains_ownership(response):
    sensor = NS(id=42, is_alive=False)
    client = NS(apply_batch_sync=lambda *args: response)
    carla = NS(command=NS(DestroyActor=lambda actor_id: actor_id))
    remaining, errors = destroy_owned_sensors([sensor], client=client, carla=carla)
    assert remaining == [sensor] and errors


def test_timeout_retains_every_owned_sensor():
    def timeout(*args):
        raise TimeoutError('RPC timed out')
    sensors = [NS(id=42), NS(id=43)]
    remaining, errors = destroy_owned_sensors(sensors, client=NS(apply_batch_sync=timeout),
        carla=NS(command=NS(DestroyActor=lambda actor_id: actor_id)))
    assert remaining == sensors and 'unconfirmed' in errors[0]


def test_no_client_fallback_reports_false_even_with_stale_snapshot():
    sensor = NS(is_alive=False, destroy=lambda: False)
    remaining, errors = destroy_owned_sensors([sensor])
    assert remaining == [sensor] and 'returned false' in errors[0]


def test_invalid_ids_never_reach_rpc():
    def forbidden(*args):
        pytest.fail('invalid ID reached RPC')
    sensor = NS(id=True)
    remaining, errors = destroy_owned_sensors([sensor], client=NS(apply_batch_sync=forbidden))
    assert remaining == [sensor] and 'Invalid' in errors[0]

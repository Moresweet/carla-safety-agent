"""Opt-in idle-world probe: destroy a just-created, never-listened sensor by ID."""
import json
import time
import uuid

import carla

from carla_safety_agent.owned_sensors import destroy_owned_sensors
from carla_safety_agent.world_health import observe_idle
from regression_material_slots import ROOT, request


def main():
    assert request('/system/preflight')['ready']
    assert request('/batches/scheduler')['scheduler']['state'] != 'running'
    client = carla.Client('127.0.0.1', 2000)
    client.set_timeout(10)
    world = client.get_world()
    before = observe_idle(client, world.get_map().name, seconds=1)
    # No map load, tick, settings change, parent vehicle or global deletion.
    blueprint = world.get_blueprint_library().find('sensor.other.gnss')
    blueprint.set_attribute('role_name', 'owned-cleanup-probe-'+uuid.uuid4().hex)
    owned = []
    report = {'scope': 'Immediate owned-sensor cleanup; no SIGKILL recovery claim',
              'before': before}
    try:
        sensor = world.spawn_actor(blueprint, carla.Transform(carla.Location(z=20)))
        owned.append(sensor)
        report.update(actor_id=sensor.id, cached_is_alive=sensor.is_alive)
        owned, errors = destroy_owned_sensors(owned, client=client, carla=carla)
        assert not errors and not owned, errors
        deadline = time.monotonic()+5
        while world.get_snapshot().find(sensor.id) is not None and time.monotonic() < deadline:
            time.sleep(.05)
        assert world.get_snapshot().find(sensor.id) is None, 'Destroyed actor remains in snapshot'
        report['after'] = observe_idle(client, world.get_map().name)
        assert report['after']['episode'] == before['episode']
        report['passed'] = True
        output = ROOT/'runs/validation'/('owned-sensor-cleanup-'+uuid.uuid4().hex+'.json')
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2))
        print(output, flush=True)
        print(json.dumps(report), flush=True)
    finally:
        if owned:
            _, errors = destroy_owned_sensors(owned, client=client, carla=carla)
            if errors:
                raise RuntimeError('Probe cleanup unconfirmed: '+'; '.join(errors))


if __name__ == '__main__':
    main()

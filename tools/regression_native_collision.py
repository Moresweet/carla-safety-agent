"""Opt-in local collision sensor experiment; creates and removes only test actors.

Requires an idle asynchronous world. Never ticks, changes maps/settings, or uses
existing actors as targets. Not a driving benchmark or full capture regression.
"""
import json
import time
import uuid

from carla_safety_agent.collision_events import CollisionEvents
from regression_material_slots import request


def main():
    import carla
    assert request('/system/preflight')['ready'], 'Studio must be idle'
    client = carla.Client('127.0.0.1', 2000)
    client.set_timeout(5)
    world = client.get_world()
    assert not world.get_settings().synchronous_mode, 'Requires asynchronous world'
    actors = []
    sensor = None
    role = 'collision-regression-' + uuid.uuid4().hex
    log = CollisionEvents()
    result = None
    try:
        blueprint = world.get_blueprint_library().find('vehicle.lincoln.mkz_2020')
        blueprint.set_attribute('role_name', role)
        for transform in world.get_map().get_spawn_points()[:50]:
            # Keep the experiment away from pre-existing dynamic actors.
            if any(actor.get_location().distance(transform.location) < 15
                   for actor in world.get_actors() if actor.type_id.startswith(('vehicle.', 'walker.'))):
                continue
            ego = world.try_spawn_actor(blueprint, transform)
            if ego is not None:
                actors.append(ego)
                break
        else:
            raise RuntimeError('No isolated free spawn point for collision experiment')
        ego.apply_control(carla.VehicleControl(brake=1, hand_brake=True))
        sensor = world.spawn_actor(world.get_blueprint_library().find('sensor.other.collision'),
                                   carla.Transform(), attach_to=ego)
        actors.append(sensor)
        sensor.listen(log.receive)
        start = world.get_snapshot().frame
        elevated = ego.get_transform()
        elevated.location.z += 4
        falling = world.try_spawn_actor(blueprint, elevated)
        if falling is None:
            raise RuntimeError('Collision-test second vehicle spawn rejected')
        actors.append(falling)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            observations = log.snapshot(start)
            hits = [event for event in observations['events'] if event['other_actor_id'] == falling.id]
            if hits:
                assert all(sum(value*value for value in event['normal_impulse'].values()) > 0 for event in hits)
                result = {'map':world.get_map().name, 'source':observations['source'],
                          'events':hits, 'dropped':observations['buffer_dropped_since_sensor_start']}
                break
            world.wait_for_tick(2)
        else:
            raise AssertionError('No native collision observation between test vehicles')
    finally:
        errors = []
        if sensor is not None:
            try: sensor.stop()
            except Exception as exc: errors.append(str(exc))
        for actor in reversed(actors):
            try:
                if actor.is_alive and actor.destroy() is False:
                    errors.append(f'Failed to destroy test actor {actor.id}')
            except Exception as exc: errors.append(str(exc))
        if errors: raise RuntimeError(f'Test cleanup incomplete: {errors}')
    assert result is not None
    # get_actors uses the last received episode snapshot; destruction acknowledgements
    # can precede that snapshot. Observe a fresh update without taking tick ownership.
    deadline = time.monotonic() + 5
    owned_ids = {actor.id for actor in actors}
    while time.monotonic() < deadline:
        world.wait_for_tick(2)
        if not owned_ids.intersection(actor.id for actor in world.get_actors()):
            break
    else:
        raise AssertionError('Test actors still present in fresh world snapshots')
    assert not world.get_settings().synchronous_mode
    result['test_actors_cleaned'] = True
    print(json.dumps(result))


if __name__ == '__main__':
    main()

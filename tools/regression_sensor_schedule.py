"""Opt-in native IMU tick-interval comparison, without model inference."""
import json
import threading
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
    original = world.get_settings()
    sensors, frames = [], {'interval': set(), 'every_tick': set()}
    condition = threading.Condition()
    report = {'before': before, 'fixed_delta_seconds': .05, 'missing': {key: [] for key in frames}}
    try:
        settings = world.get_settings()
        settings.synchronous_mode = True
        settings.fixed_delta_seconds = .05
        world.apply_settings(settings)
        for name, interval in [('interval', '.05'), ('every_tick', '0')]:
            blueprint = world.get_blueprint_library().find('sensor.other.imu')
            blueprint.set_attribute('sensor_tick', interval)
            sensor = world.spawn_actor(blueprint, carla.Transform(carla.Location(z=20)))
            sensors.append(sensor)
            def callback(data, name=name):
                with condition:
                    frames[name].add(data.frame)
                    condition.notify_all()
            sensor.listen(callback)
        for index in range(110):
            frame = world.tick(10)
            with condition:
                condition.wait_for(lambda: all(frame in values for values in frames.values()), timeout=.5)
                if index >= 10:
                    for name, values in frames.items():
                        if frame not in values:
                            report['missing'][name].append(frame)
        report['sampled_frames'] = 100
    finally:
        stop_errors = []
        for sensor in sensors:
            try:
                sensor.stop()
            except Exception as exc:
                stop_errors.append(str(exc))
        try:
            _, errors = destroy_owned_sensors(sensors, client=client, carla=carla)
            if errors or stop_errors:
                raise RuntimeError('; '.join(errors+stop_errors))
        finally:
            world.apply_settings(original)
    report['after'] = observe_idle(client, world.get_map().name)
    output = ROOT/'runs/validation'/('sensor-schedule-'+uuid.uuid4().hex+'.json')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2))
    print(output, flush=True)
    print(json.dumps(report), flush=True)
    assert not report['missing']['every_tick'], 'Every-tick IMU failed its frame contract'


if __name__ == '__main__':
    main()

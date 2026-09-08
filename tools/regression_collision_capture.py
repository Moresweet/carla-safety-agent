"""Opt-in full capture collision test; the normal worker remains sole tick owner."""
import json
import time
import uuid

from carla_safety_agent.replay import replay_events
from regression_material_slots import ROOT, request


def main():
    import carla
    assert request('/system/preflight')['ready'], 'Requires idle studio'
    client = carla.Client('127.0.0.1', 2000)
    client.set_timeout(5)
    world = client.get_world()
    assert not world.get_settings().synchronous_mode
    assert not list(world.get_actors().filter('sensor.*')), 'Requires no pre-existing sensors'
    request('/collection/start', {'mode':'stationary', 'frames':120, 'every':2, 'max_frames':120})
    execution = request('/session/status')['session']['run_id']
    falling = None
    report_path = ROOT/'.runtime/evaluation-control/sensor-rig-status.json'
    dataset = None
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            state = request('/session/status')['session']
            assert state['run_id'] == execution
            if state['state'] in ('failed','completed','stopped'):
                raise RuntimeError(f'Capture ended before test contact: {state["state"]}')
            if report_path.exists():
                report = json.loads(report_path.read_text())
                candidate = ROOT/'.runtime/generated-scenarios'/str(report.get('run_id',''))
                manifest = candidate/'manifest.json'
                if manifest.is_file() and json.loads(manifest.read_text()).get('execution_id') == execution:
                    vehicles = [actor for actor in world.get_actors().filter('vehicle.*')
                                if actor.attributes.get('role_name') == 'sensor_rig']
                    if len(vehicles) == 1 and report.get('frames',0) >= 3:
                        dataset = candidate
                        ego = vehicles[0]
                        break
            time.sleep(.05)
        else:
            raise TimeoutError('Capture vehicle not ready')
        blueprint = world.get_blueprint_library().find('vehicle.lincoln.mkz_2020')
        blueprint.set_attribute('role_name', 'capture-contact-'+uuid.uuid4().hex)
        transform = ego.get_transform()
        transform.location.z += 4
        falling = world.try_spawn_actor(blueprint, transform)
        if falling is None: raise RuntimeError('Test contact vehicle spawn rejected')
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            state = request('/session/status')['session']
            assert state['run_id'] == execution
            if state['state'] in ('completed','stopped','failed') or (state['state']=='recovering' and state.get('error')): break
            time.sleep(.25)
        else: raise TimeoutError('Collision capture did not finish')
        assert state['state'] == 'completed', state
        report = json.loads(report_path.read_text())
        assert not report['cleanup_errors'], report
        events = replay_events(dataset.parent, dataset.name)
        hits = [event for event in events['collisions']['events'] if event['other_actor_id'] == falling.id]
        assert hits, 'Native test collision missing from saved dataset'
        assert all(event['replay_frame'] is not None for event in hits)
        assert json.loads((dataset/'manifest.json').read_text())['files']['collisions']=='collisions.json'
        print(json.dumps({'execution_id':execution,'dataset':dataset.name,'collisions':hits,
                          'samples':events['sample_count']}), flush=True)
    finally:
        # A failed actor RPC must not prevent stopping our still-live worker.
        try:
            if falling is not None and falling.is_alive:
                if falling.destroy() is False: raise RuntimeError('Test contact vehicle cleanup failed')
        finally:
            current = request('/session/status')['session']
            if current['run_id'] == execution and current['state'] in ('preparing','running','stopping'):
                request('/collection/stop', {'run_id':execution})
    world.wait_for_tick(5)
    assert not world.get_settings().synchronous_mode
    assert not list(world.get_actors().filter('sensor.*'))
    assert not [actor for actor in world.get_actors().filter('vehicle.*')
                if actor.attributes.get('role_name') == 'sensor_rig' or actor.id == falling.id]
    print('Collision capture and native cleanup verified', flush=True)


if __name__ == '__main__':
    main()

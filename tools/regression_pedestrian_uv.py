"""Actual browser UV editing of one owned walker, with an untouched control."""
import argparse
import json
import math
import subprocess
import time
import uuid

import carla

from carla_safety_agent.world_health import observe_idle
from regression_material_slots import ROOT, request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--node', required=True)
    args = parser.parse_args()
    assert request('/system/preflight')['ready']
    session_id = request('/session/status')['session']['run_id']
    assert request('/batches/scheduler')['scheduler']['state'] != 'running'
    client = carla.Client('127.0.0.1', 2000)
    client.set_timeout(10)
    world = client.get_world()
    before = observe_idle(client, world.get_map().name, seconds=1)
    camera = world.get_spectator().get_transform()
    spawn = world.get_map().get_spawn_points()[0]
    output = ROOT/'runs/validation'/('pedestrian-uv-'+uuid.uuid4().hex)
    output.mkdir(parents=True, exist_ok=False)
    report = {'state': 'started', 'before': before, 'owned_actor_ids': [],
              'scope': 'Slot 14 source UV and actual scene comparison; bind pose is not live animation'}
    owned = report['owned_actor_ids']

    def save():
        (output/'report.json').write_text(json.dumps(report, indent=2))

    def image(actor_id, name):
        actor = world.get_actor(actor_id)
        assert actor and actor.type_id == 'walker.pedestrian.0001'
        transform = actor.get_transform()
        center = carla.Location(actor.bounding_box.location.x, actor.bounding_box.location.y,
                                actor.bounding_box.location.z)
        transform.transform(center)
        eye = center + transform.get_forward_vector()*3.2 + transform.get_right_vector()*.8 + carla.Location(z=.4)
        delta = center-eye
        rotation = carla.Rotation(pitch=math.degrees(math.atan2(delta.z, math.hypot(delta.x, delta.y))),
                                  yaw=math.degrees(math.atan2(delta.y, delta.x)))
        world.get_spectator().set_transform(carla.Transform(eye, rotation))
        time.sleep(.2)
        (output/name).write_bytes(request('/scene/preview', raw=True))

    try:
        for offset in (3, 6):
            location = spawn.location + spawn.get_right_vector()*offset
            result = request('/objects/spawn', {'blueprint_id': 'walker.pedestrian.0001',
                'transform': {'location': {'x': location.x, 'y': location.y, 'z': location.z+1},
                              'rotation': {'yaw': spawn.rotation.yaw}, 'snap_to_ground': True}})
            owned.append(result['object']['id'])
            save()
        deadline = time.monotonic()+5
        while time.monotonic() < deadline and not all(world.get_snapshot().find(actor_id) for actor_id in owned):
            time.sleep(.05)
        time.sleep(.5)
        image(owned[0], 'target-before.jpg')
        image(owned[1], 'control-before.jpg')
        browser = subprocess.run([args.node, str(ROOT/'tools/browser_reviewed_models.mjs'),
            '--uv-convention', '--pedestrian-id', str(owned[0]), '--texture',
            str(ROOT/'runs/validation/material-slots-20260908/uv-calibration.png'),
            '--apply-pedestrian'], cwd=ROOT, capture_output=True, text=True, timeout=240)
        (output/'browser.log').write_text(browser.stdout+'\n'+browser.stderr)
        if browser.returncode:
            raise RuntimeError('Browser UV test failed; see '+str(output/'browser.log'))
        report['browser'] = json.loads(browser.stdout.strip().splitlines()[-1])
        image(owned[0], 'target-applied.jpg')
        # Focus currently creates an eight-second native debug box. Preserve
        # the immediate image and compare after its lifetime, without clearing
        # another user's debug geometry or changing the applied texture.
        time.sleep(9)
        image(owned[0], 'target-applied-after-highlight.jpg')
        image(owned[1], 'control-after.jpg')
        report.update(state='execution_verified', visual_review_required=True)
    except BaseException as exc:
        report.update(state='failed', error=str(exc))
        raise
    finally:
        errors = []
        current = request('/session/status')['session']
        if current['run_id'] != session_id or client.get_world().id != before['episode']:
            errors.append('World/session changed: do not mutate another owner')
        else:
            for actor_id in owned:
                try:
                    request('/objects/delete', {'actor_id': actor_id})
                except Exception as exc:
                    errors.append(str(exc))
            try:
                world.get_spectator().set_transform(camera)
                report['after'] = observe_idle(client, before['map'])
            except Exception as exc:
                errors.append(str(exc))
        report['cleanup_errors'] = errors
        save()
        print(output, flush=True)
        if errors:
            raise RuntimeError('UV probe cleanup needs review: '+'; '.join(errors))


if __name__ == '__main__':
    main()

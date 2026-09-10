"""Actual browser UV editing of one owned walker, with an untouched control."""
import argparse
import json
import math
import subprocess
import time
import uuid
from pathlib import Path
from PIL import Image

import carla

from carla_safety_agent.world_health import observe_idle
from regression_material_slots import ROOT, request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--node', required=True)
    parser.add_argument('--vehicle', action='store_true', help='Test Audi A2 source UV instead of walker pants')
    parser.add_argument('--restart-bridge',action='store_true',help='Verify saved runtime identity after a bridge restart')
    parser.add_argument('--exact-slot-restore',action='store_true',help='Probe Audi A2 exact slot apply and native original-material restore')
    args = parser.parse_args()
    if args.exact_slot_restore and not args.vehicle:parser.error('Exact slot probe currently covers Audi A2 only')
    kind = 'vehicle' if args.vehicle else 'pedestrian'
    blueprint = 'vehicle.audi.a2' if args.vehicle else 'walker.pedestrian.0001'
    assert request('/system/preflight')['ready']
    session_id = request('/session/status')['session']['run_id']
    assert request('/batches/scheduler')['scheduler']['state'] != 'running'
    client = carla.Client('127.0.0.1', 2000)
    client.set_timeout(10)
    world = client.get_world()
    before = observe_idle(client, world.get_map().name, seconds=1)
    camera = world.get_spectator().get_transform()
    spawn = world.get_map().get_spawn_points()[0]
    output = ROOT/'runs/validation'/(kind+'-uv-'+uuid.uuid4().hex)
    output.mkdir(parents=True, exist_ok=False)
    report = {'state': 'started', 'before': before, 'owned_actor_ids': [],
              'scope': blueprint+' source UV and actual scene comparison; not live animation'}
    owned = report['owned_actor_ids']

    def save():
        (output/'report.json').write_text(json.dumps(report, indent=2))

    def image(actor_id, name):
        actor = world.get_actor(actor_id)
        assert actor and actor.type_id == blueprint
        transform = actor.get_transform()
        center = carla.Location(actor.bounding_box.location.x, actor.bounding_box.location.y,
                                actor.bounding_box.location.z)
        transform.transform(center)
        eye = center + transform.get_forward_vector()*(4.5 if args.vehicle else 3.2) + transform.get_right_vector()*(5 if args.vehicle else .8) + carla.Location(z=1.7 if args.vehicle else .4)
        delta = center-eye
        rotation = carla.Rotation(pitch=math.degrees(math.atan2(delta.z, math.hypot(delta.x, delta.y))),
                                  yaw=math.degrees(math.atan2(delta.y, delta.x)))
        world.get_spectator().set_transform(carla.Transform(eye, rotation))
        time.sleep(.2)
        (output/name).write_bytes(request('/scene/preview', raw=True))

    try:
        for offset in ((0, 7) if args.vehicle else (3, 6)):
            location = spawn.location + spawn.get_right_vector()*offset
            result = request('/objects/spawn', {'blueprint_id': blueprint,
                'transform': {'location': {'x': location.x, 'y': location.y, 'z': location.z+1},
                              'rotation': {'yaw': spawn.rotation.yaw}, 'snap_to_ground': True}})
            owned.append(result['object']['id'])
            save()
        deadline = time.monotonic()+5
        while time.monotonic() < deadline and not all(world.get_snapshot().find(actor_id) for actor_id in owned):
            time.sleep(.05)
        time.sleep(.5)
        if args.restart_bridge:
            subprocess.run(['bash',str(ROOT/'scripts/restart_studio_bridge.sh')],cwd=ROOT,check=True,capture_output=True,text=True)
            assert client.get_world().id==before['episode']
            report['bridge_restarted_before_texture']=True
        image(owned[0], 'target-before.jpg')
        image(owned[1], 'control-before.jpg')
        browser_args=[args.node, str(ROOT/'tools/browser_reviewed_models.mjs'),
            '--uv-convention', '--'+kind+'-id', str(owned[0]), '--texture',
            str(ROOT/'runs/validation/material-slots-20260908/uv-calibration.png')]
        if not args.exact_slot_restore:browser_args.append('--apply-'+kind)
        browser = subprocess.run(browser_args, cwd=ROOT, capture_output=True, text=True, timeout=240)
        (output/'browser.log').write_text(browser.stdout+'\n'+browser.stderr)
        if browser.returncode:
            raise RuntimeError('Browser UV test failed; see '+str(output/'browser.log'))
        report['browser'] = json.loads(browser.stdout.strip().splitlines()[-1])
        if args.exact_slot_restore:
            from carla_safety_agent.provenance import ActorProvenance
            record=ActorProvenance(ROOT/'.runtime/actor-provenance.json').records(world.id)[str(owned[0])]
            name=record['runtime_object_name'];assert name in world.get_names_of_all_objects()
            atlas=Image.open(Path(report['browser']['output'])/'vehicle-atlas.png').convert('RGBA')
            texture=carla.TextureColor(*atlas.size)
            for y in range(atlas.height):
                for x in range(atlas.width):texture.set(x,y,carla.Color(*atlas.getpixel((x,y))))
            world.apply_color_texture_to_object(name+'|csa|VehicleMesh|4|apply',carla.MaterialParameter.Diffuse,texture)
        image(owned[0], 'target-applied.jpg')
        # Focus currently creates an eight-second native debug box. Preserve
        # the immediate image and compare after its lifetime, without clearing
        # another user's debug geometry or changing the applied texture.
        if not args.exact_slot_restore:time.sleep(9)
        image(owned[0], 'target-applied-after-highlight.jpg')
        image(owned[1], 'control-after.jpg')
        if args.exact_slot_restore:
            world.apply_color_texture_to_object(name+'|csa|VehicleMesh|4|restore',carla.MaterialParameter.Diffuse,carla.TextureColor(1,1))
            image(owned[0],'target-restored.jpg')
            report['exact_slot_apply_and_restore']=True
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

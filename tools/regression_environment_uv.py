"""Apply a browser-generated atlas to one verified environment slot and restore."""
import argparse
import json
import math
import time
import urllib.parse
import uuid
from pathlib import Path

import carla

from carla_safety_agent.world_health import observe_idle
from regression_material_slots import ROOT, request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--atlas', required=True)
    args = parser.parse_args()
    atlas = Path(args.atlas).resolve()
    assert ROOT/'runs/validation' in atlas.parents and atlas.is_file()
    assert request('/system/preflight')['ready']
    session = request('/session/status')['session']['run_id']
    assert request('/batches/scheduler')['scheduler']['state'] != 'running'
    client = carla.Client('127.0.0.1', 2000)
    client.set_timeout(10)
    world = client.get_world()
    before = observe_idle(client, world.get_map().name, seconds=1)
    camera = world.get_spectator().get_transform()
    target = 'SM_GasStation01_13'
    objects = request('/catalog/objects?'+urllib.parse.urlencode(
        {'category': 'buildings', 'q': target, 'limit': 200}))['objects']
    obj = next(o for o in objects if o['name'] == target+'_SM_0')
    catalog = request('/materials/catalog?object_id='+str(obj['id']))
    assert catalog['target'] == target and not catalog['overrides']
    selection = {'object_id': str(obj['id']), 'component': 'StaticMeshComponent0', 'slot': '0'}
    output = ROOT/'runs/validation'/('environment-uv-'+uuid.uuid4().hex)
    output.mkdir(parents=True, exist_ok=False)
    report = {'state': 'started', 'before': before, 'selection': selection, 'atlas': str(atlas)}
    applied = False
    try:
        loc = obj['location']
        center = carla.Location(**loc)
        eye = center + carla.Location(x=-12, y=-12, z=18)
        delta = center-eye
        rotation = carla.Rotation(pitch=math.degrees(math.atan2(delta.z, math.hypot(delta.x, delta.y))),
                                  yaw=math.degrees(math.atan2(delta.y, delta.x)))
        world.get_spectator().set_transform(carla.Transform(eye, rotation))
        time.sleep(.2)
        (output/'before.jpg').write_bytes(request('/scene/preview', raw=True))
        applied = True  # An RPC timeout may occur after native mutation.
        report['apply'] = request('/materials/apply?'+urllib.parse.urlencode(selection), atlas.read_bytes())
        (output/'applied.jpg').write_bytes(request('/scene/preview', raw=True))
        report.update(state='execution_verified', visual_review_required=True)
    except BaseException as exc:
        report.update(state='failed', error=str(exc))
        raise
    finally:
        try:
            assert request('/session/status')['session']['run_id'] == session and client.get_world().id == before['episode'], 'World owner changed; manual recovery required'
            if applied:
                report['restore'] = request('/materials/restore', selection)
                assert not request('/materials/catalog?object_id='+str(obj['id']))['overrides']
                (output/'restored.jpg').write_bytes(request('/scene/preview', raw=True))
            world.get_spectator().set_transform(camera)
            report['after'] = observe_idle(client, before['map'])
        except BaseException as exc:
            report.update(state='recovery_failed', cleanup_error=str(exc))
            raise
        finally:
            (output/'report.json').write_text(json.dumps(report, indent=2))
            print(output, flush=True)


if __name__ == '__main__':
    main()

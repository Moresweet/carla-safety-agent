#!/usr/bin/env python3
"""Opt-in live regression; use an idle world. Only deletes actors it creates."""
import argparse
import io
import json
import time
import queue
import urllib.request
import urllib.error
from pathlib import Path

import carla
from PIL import Image
import numpy as np


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    report = []
    created = []

    def request(path, data=None, png=None):
        body = png if png is not None else json.dumps(data).encode() if data is not None else None
        headers = {'Content-Type': 'image/png' if png is not None else 'application/json'}
        try:
            with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8765/'+path, data=body, headers=headers), timeout=120) as r:
                return json.load(r)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(exc.read().decode()) from exc

    def check(name, fn):
        start = time.monotonic()
        try:
            result = fn()
            report.append({'name': name, 'passed': True, 'details': result})
        except Exception as exc:
            report.append({'name': name, 'passed': False, 'error': str(exc)})
        report[-1]['seconds'] = round(time.monotonic()-start, 2)
        (output/'report.json').write_text(json.dumps(report, indent=2))
        print(json.dumps(report[-1]), flush=True)

    status = request('e2e/status')
    assert status['job']['state'] not in ('running', 'stopping'), 'Stop evaluation first'
    client = carla.Client('127.0.0.1', 2000)
    client.set_timeout(20)
    world = client.get_world()
    assert not world.get_settings().synchronous_mode, 'Requires idle asynchronous world'
    check('categories', lambda: request('catalog/categories'))
    for category in ('buildings', 'walls', 'bridges', 'roads', 'vegetation', 'vehicles', 'pedestrians', 'spawned_props'):
        check('catalog:'+category, lambda category=category: request('catalog/objects?category='+category+'&limit=2'))
    check('natural-language', lambda: request('scenario/compile', {'description':'Town04 前车在18米处急刹，自车速度15 m/s', 'seed':90601}))
    points = world.get_map().get_spawn_points()
    texture = io.BytesIO()
    Image.new('RGB', (64,64), (255,0,160)).save(texture, format='PNG')

    def actor_test(blueprint, index):
        t = next(p for p in points[index:] if all(p.location.distance(a.get_location()) > 20
                 for a in world.get_actors() if a.type_id.startswith(('vehicle.', 'walker.', 'static.prop.'))))
        obj = request('objects/spawn', {'blueprint_id':blueprint, 'transform':{
            'location':{'x':t.location.x,'y':t.location.y,'z':t.location.z},
            'rotation':{'yaw':t.rotation.yaw}, 'snap_to_ground':True}})['object']
        created.append((obj['id'], blueprint))
        actor = world.get_actor(obj['id'])
        first = actor.get_location()
        time.sleep(2)
        drift = first.distance(actor.get_location())
        if blueprint.startswith('vehicle.'):
            assert drift < 0.05, f'Editor vehicle drifted {drift}m'
        assert obj.get('origin') == 'user', 'Missing user-created marker'
        assert 'rotation' in obj, 'Missing editable rotation'
        state = request('scene/state')
        assert any(o['id']==actor.id for o in state['objects']), 'Actor absent from BEV'
        request('focus/actor', {'actor_id':actor.id})
        request('objects/update', {'actor_id':actor.id, 'transform':{'rotation':{'yaw':35}}})
        assert abs(actor.get_transform().rotation.yaw-35) < 1, 'Update rotation failed'
        applied = None
        changed = None
        if blueprint.startswith(('vehicle.', 'walker.')):
            endpoint = 'apply' if blueprint.startswith('vehicle.') else 'apply/pedestrian'
            camera_bp = world.get_blueprint_library().find('sensor.camera.rgb')
            camera_bp.set_attribute('image_size_x', '640')
            camera_bp.set_attribute('image_size_y', '360')
            camera_bp.set_attribute('sensor_tick', '0.2')
            distance = max(4, actor.bounding_box.extent.x * 2.8)
            camera = world.spawn_actor(camera_bp, carla.Transform(carla.Location(x=-distance,y=-distance*.6,z=3),carla.Rotation(pitch=-15,yaw=30)), attach_to=actor)
            frames = queue.Queue()
            camera.listen(frames.put)
            def capture(label):
                time.sleep(1)
                while not frames.empty():
                    frames.get_nowait()
                frame = frames.get(timeout=20)
                array = np.frombuffer(frame.raw_data,np.uint8).reshape(360,640,4)[:,:,:3][:,:,::-1].copy()
                Image.fromarray(array).save(output/(blueprint+'-'+label+'.png'))
                return array.astype(np.int16)
            try:
                before = capture('before')
                applied = request(endpoint+'?actor_id='+str(actor.id), png=texture.getvalue())
                after = capture('after')
                changed = float(np.mean(np.max(np.abs(after-before),axis=2)>40))
                assert changed > 0.001, f'No visible texture change ({changed})'
            finally:
                camera.stop()
                camera.destroy()
        # Exercise duplication clear of roadside geometry after testing road placement.
        request('objects/update', {'actor_id':actor.id, 'transform':{'location':{'z':actor.get_location().z+4}}})
        duplicate = request('objects/duplicate', {'actor_id':actor.id})['object']
        created.append((duplicate['id'], blueprint))
        request('objects/delete', {'actor_id':duplicate['id']})
        assert world.get_actor(duplicate['id']) is None, 'Delete did not remove duplicate'
        return {'actor_id':actor.id, 'drift_m':drift, 'apply':applied, 'changed_pixel_fraction':changed}

    try:
        for index, blueprint in enumerate(('vehicle.tesla.model3', 'vehicle.dodge.charger_police_2020', 'vehicle.carlamotors.european_hgv', 'walker.pedestrian.0001', 'static.prop.advertisement')):
            check('actor:'+blueprint, lambda blueprint=blueprint,index=index:actor_test(blueprint,index*3))
        check('hero-lock', lambda: request('camera/hero-lock', {'enabled':True}))
        check('hero-release', lambda: request('camera/hero-lock', {'enabled':False}))
        check('bev-focus', lambda: request('focus/bev', {'x':points[0].location.x,'y':points[0].location.y}))
    finally:
        for actor_id, blueprint in reversed(created):
            actor = world.get_actor(actor_id)
            if actor and actor.type_id == blueprint:
                actor.destroy()
    assert all(r['passed'] for r in report), 'See report.json for failures'


if __name__ == '__main__':
    main()

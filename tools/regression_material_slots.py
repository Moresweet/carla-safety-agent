"""Opt-in real CARLA material apply/restore smoke test; saves visual evidence.

Requires an idle studio and the native material-slot patch. Does not prove UV
alignment or isolation by itself: inspect the captured images as well.
"""
import io
import json
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
BASE = 'http://127.0.0.1:8765'


def request(path, data=None, raw=False):
    body = data if isinstance(data, bytes) else json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(BASE + path, data=body)
    with urllib.request.urlopen(req, timeout=60) as response:
        return response.read() if raw else json.load(response)


def main():
    assert request('/system/preflight')['ready'], 'Studio must be idle'
    import carla
    client = carla.Client('127.0.0.1', 2000)
    client.set_timeout(10)
    world = client.get_world()
    spectator = world.get_spectator()
    original_camera = spectator.get_transform()
    output = ROOT / 'runs/validation/material-slots-20260908'
    output.mkdir(parents=True, exist_ok=True)
    pattern = Image.new('RGB', (1024, 1024), 'white')
    draw = ImageDraw.Draw(pattern)
    for y in range(8):
        for x in range(8):
            draw.rectangle((x*128,y*128,(x+1)*128-1,(y+1)*128-1),
                           fill=('magenta' if (x+y)%2 else 'cyan'))
    draw.rectangle((0,0,1023,48), fill='red')
    draw.rectangle((0,0,48,1023), fill='yellow')
    draw.text((70,70), 'UV TOP LEFT', fill='black', font_size=52)
    payload = io.BytesIO()
    pattern.save(payload, format='PNG')
    pattern.save(output/'uv-calibration.png')
    targets = [('SM_GasStation01_13', 0), ('SM_Church01_5', 0),
               ('Road_Road_Town04_1', 0)]
    reports = []
    try:
        for target, slot in targets:
            objects = request('/catalog/objects?' + urllib.parse.urlencode(
                {'category':'roads' if target.startswith('Road_') else 'buildings', 'q':target, 'limit':200}))['objects']
            obj = next(o for o in objects if o['name'] in (target, target+'_SM_0', target+'_SM'))
            info = request('/materials/catalog?object_id='+str(obj['id']))
            assert info['target'] == target
            component = 'StaticMeshComponent0'
            assert not info['overrides'], 'Refusing to overwrite an existing user material edit'
            selection = {'object_id':obj['id'], 'component':component, 'slot':slot}
            baseline = request('/scenes/save', {'name':'材质版本验证：'+target})
            request('/focus/environment', {'object_id':obj['id']})
            (output/(target+'-before.jpg')).write_bytes(request('/scene/preview', raw=True))
            # Restore even if a request times out after the server applied it.
            try:
                applied = request('/materials/apply?'+urllib.parse.urlencode(selection), payload.getvalue())
                assert applied['ok']
                (output/(target+'-applied.jpg')).write_bytes(request('/scene/preview', raw=True))
                head = baseline['head']
                painted = request('/scenes/save', {'name':head['name'], 'scene_id':head['scene_id'],
                                                   'expected_version':head['version']})
                if target == targets[0][0]:
                    subprocess.run(['bash', str(ROOT/'scripts/restart_studio_bridge.sh')],
                                   cwd=ROOT, check=True)
                request('/scenes/history', {'scene_id':head['scene_id'], 'direction':-1,
                                           'expected_version':painted['head']['version']})
                assert not request('/materials/catalog?object_id='+str(obj['id']))['overrides']
                request('/scenes/history', {'scene_id':head['scene_id'], 'direction':1,
                                           'expected_version':head['version']})
                edits = request('/materials/catalog?object_id='+str(obj['id']))['overrides']
                assert len(edits)==1 and edits[0]['texture']==applied['texture']
            finally:
                restored = request('/materials/restore', selection)
            assert restored['ok']
            (output/(target+'-restored.jpg')).write_bytes(request('/scene/preview', raw=True))
            assert not request('/materials/catalog?object_id='+str(obj['id']))['overrides']
            reports.append({'target':target, 'slot':slot, 'apply_restore_api':True,
                            'scene_undo_redo':True, 'scene_id':head['scene_id']})
            (output/'report.json').write_text(json.dumps({'targets':reports, 'visual_review_required':True}, indent=2))
            print(json.dumps(reports[-1]), flush=True)
    finally:
        spectator.set_transform(original_camera)


if __name__ == '__main__':
    main()

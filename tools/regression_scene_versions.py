"""Explicit local smoke test: create a prop, version it, restart, restore, clean up."""
import json
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def request(path, data=None):
    req = urllib.request.Request('http://127.0.0.1:8765/'+path,
        data=json.dumps(data).encode() if data is not None else None,
        headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def main():
    assert request('system/preflight')['ready']
    owned = set()
    try:
        prop = request('objects/spawn', {'blueprint_id':'static.prop.advertisement',
            'transform':{'location':{'x':393.098,'y':-228.088,'z':2.5}}})['object']
        owned.add(prop['id'])
        first = request('scenes/save', {'name':'验证：场景版本与重启恢复'})
        stable = next(o['stable_id'] for o in first['document']['objects']
                      if o['blueprint_id'] == 'static.prop.advertisement' and abs(o['transform']['location']['x']-393.098)<.01)
        head = first['head']
        request('objects/update', {'actor_id':prop['id'],'transform':{'location':{'x':398.098}}})
        second = request('scenes/save', {'name':head['name'],'scene_id':head['scene_id'],'expected_version':head['version']})
        restored = request('scenes/history', {'scene_id':head['scene_id'],'expected_version':second['head']['version'],'direction':-1})
        assert restored['head']['version'] == head['version']
        request('objects/delete', {'actor_id':prop['id']})
        owned.remove(prop['id'])
        subprocess.run(['bash', str(ROOT/'scripts/restart_studio_bridge.sh')], cwd=ROOT, check=True)
        restored = request('scenes/restore', {'scene_id':head['scene_id']})
        replacement = restored['bindings'][stable]
        owned.add(replacement)
        assert replacement != prop['id']
        listing = request('catalog/objects?category=spawned_props&origin=user')['objects']
        actor = next(o for o in listing if o['id'] == replacement)
        assert abs(actor['location']['x']-393.098)<.01
        report = {'passed': True, 'scene_id':head['scene_id'], 'stable_id':stable,
                  'actor_before':prop['id'], 'actor_after':replacement, 'position':actor['location']}
        output = ROOT/'runs/validation/scene-versions-20260908.json'
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2))
        print(json.dumps(report), flush=True)
    finally:
        for actor_id in owned:
            request('objects/delete', {'actor_id':actor_id})


if __name__ == '__main__': main()

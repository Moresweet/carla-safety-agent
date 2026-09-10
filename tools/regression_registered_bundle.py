"""Restore a single generated-object bundle with an existing new registry binding."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import uuid

from carla_safety_agent.project_bundle import read_bundle
from carla_safety_agent.blender_pipeline import BlenderPipeline
from regression_material_slots import ROOT, request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    args = parser.parse_args()
    _, files = read_bundle(args.archive)
    heads = [json.loads(p) for n,p in files.items() if n.startswith('scenes/') and n.endswith('/head.json')]
    assert len(heads) == 1
    head = heads[0]
    document = json.loads(files[f'scenes/{head["scene_id"]}/{head["version"]}.json'])
    assert len(document['objects']) == 1
    target = document['objects'][0]; stable = target['stable_id']
    entry = BlenderPipeline(ROOT).registry()[target['blueprint_id']]
    assert entry['import_returncode'] == 0
    assert request('/system/preflight')['ready']
    assert request('/batches/scheduler')['scheduler']['state'] != 'running'
    baseline = request('/scenes/save', {'name':'重映射场景恢复前基线'})
    assert stable not in {o['stable_id'] for o in baseline['document']['objects']}
    staged = subprocess.run([sys.executable, str(ROOT/'tools/project_bundle.py'), 'stage',
                             str(args.archive), '--project', str(ROOT)], check=True, capture_output=True, text=True)
    bundle_id = json.loads(staged.stdout)['bundle_id']
    output = ROOT/'runs/validation'/('registered-bundle-'+uuid.uuid4().hex)
    output.mkdir()
    actor_id = None
    try:
        restored = request('/scenes/restore-bundle', {'bundle_id':bundle_id,
            'scene_id':head['scene_id'], 'version':head['version']})
        actor_id = restored['bindings'][stable]
        import carla
        client = carla.Client('127.0.0.1',2000); client.set_timeout(10)
        world = client.get_world(); actor = world.get_actor(actor_id)
        assert actor.attributes['mesh_path'] == entry['mesh_path']
        dimensions = [getattr(actor.bounding_box.extent,k)*2 for k in ('x','y','z')]
        request('/focus/actor', {'actor_id':actor_id})
        (output/'spawned.jpg').write_bytes(request('/scene/preview', raw=True))
        repeated = request('/scenes/restore-bundle', {'bundle_id':bundle_id,
            'scene_id':head['scene_id'], 'version':head['version']})
        assert repeated['spawned'] == 0 and repeated['bindings'][stable] == actor_id
        report = {'bundle_id':bundle_id, 'blueprint_id':target['blueprint_id'], 'actor_id':actor_id,
                  'mesh_path_verified':True, 'dimensions_m':dimensions, 'duplicate_avoided':True,
                  'visual_review_required':True}
    finally:
        if actor_id is not None: request('/objects/delete', {'actor_id':actor_id})
        request('/scenes/restore', {'scene_id':baseline['head']['scene_id'],'version':baseline['head']['version']})
    assert world.wait_for_tick(10).find(actor_id) is None
    report['test_actor_removed'] = True
    (output/'report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({'output':str(output), **report}),flush=True)


if __name__ == '__main__': main()

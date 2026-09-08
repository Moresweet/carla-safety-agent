"""Opt-in native restore of staged material scenes, followed by baseline restore."""
import json
import subprocess
import sys
import tempfile
import urllib.parse
from pathlib import Path

from carla_safety_agent.project_bundle import read_bundle
from regression_material_slots import ROOT, request


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    args = parser.parse_args()
    manifest, files = read_bundle(args.archive)
    selected = []
    for name, payload in files.items():
        if not name.startswith('scenes/') or name.endswith('/head.json'): continue
        document = json.loads(payload)
        if document.get('environment_materials'):
            assert not document['objects'], 'Material regression must not create historical actors'
            selected.append(document)
    assert selected, 'Need material-bearing scene versions'
    assert request('/system/preflight')['ready']
    assert request('/batches/scheduler')['scheduler']['state'] != 'running'
    staged = subprocess.run([sys.executable, str(ROOT/'tools/project_bundle.py'), 'stage',
        str(args.archive), '--project', str(ROOT)], check=True, capture_output=True, text=True)
    bundle_id = json.loads(staged.stdout)['bundle_id']
    output = Path(tempfile.mkdtemp(prefix='bundle-restore-', dir=ROOT/'runs/validation'))
    baseline = request('/scenes/save', {'name': '迁移包恢复验证前基线'})
    reports = []
    try:
        for document in selected:
            restored = request('/scenes/restore-bundle', {'bundle_id':bundle_id,
                'scene_id':document['scene_id'], 'version':document['version']})
            assert restored['ok'] and not restored['scene_history_installed']
            observed = request('/scenes/save', {'name':'迁移包恢复验证结果'})['document']
            assert observed['environment_materials'] == document['environment_materials']
            for edit in document['environment_materials']:
                target = edit['target']
                query = urllib.parse.urlencode({'category':'roads' if target.startswith('Road_') else 'buildings',
                                              'q':target, 'limit':200})
                objects = request('/catalog/objects?'+query)['objects']
                obj = next(obj for obj in objects if obj['name'] in (target,target+'_SM_0',target+'_SM'))
                request('/focus/environment', {'object_id':obj['id']})
                (output/(document['version']+'-'+target+'.jpg')).write_bytes(request('/scene/preview',raw=True))
            reports.append({'scene_id':document['scene_id'], 'version':document['version'],
                            'materials_verified':len(document['environment_materials'])})
    finally:
        request('/scenes/restore', {'scene_id':baseline['head']['scene_id'], 'version':baseline['head']['version']})
    after = request('/scenes/save', {'name':'迁移验证清理确认'})['document']
    for key in ('objects','environment_materials','hidden_environment'):
        assert after[key] == baseline['document'][key], key
    import carla
    client = carla.Client('127.0.0.1',2000); client.set_timeout(10)
    world = client.get_world()
    assert not world.get_settings().synchronous_mode
    assert not list(world.get_actors().filter('sensor.*'))
    result = {'passed':True,'bundle_id':bundle_id,'scenes':reports,'baseline_restored':True,
              'native_cleanup_verified':True,'visual_review_required':True,
              'scope':'Same-map material scene restoration on existing native assets'}
    (output/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'output':str(output),**result}),flush=True)


if __name__ == '__main__': main()

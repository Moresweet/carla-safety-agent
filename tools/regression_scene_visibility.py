"""Real idle-CARLA visibility persistence smoke test; restore all test changes."""
import json
import subprocess
from regression_material_slots import ROOT, request


def main():
    assert request('/system/preflight')['ready']
    target = request('/catalog/objects?category=buildings&q=SM_GasStation01_13&limit=50')['objects'][0]
    assert target['name'] == 'SM_GasStation01_13_SM_0'
    baseline = request('/scenes/save', {'name':'可见性版本实机验证'})
    assert str(target['id']) not in {r['object_id'] for r in baseline['document']['hidden_environment']}
    output = ROOT/'runs/validation/scene-visibility-20260908'
    output.mkdir(parents=True, exist_ok=True)
    head = baseline['head']
    try:
        request('/focus/environment', {'object_id':target['id']})
        (output/'visible.jpg').write_bytes(request('/scene/preview', raw=True))
        request('/objects/environment/visibility', {'object_id':target['id'],'visible':False})
        (output/'hidden.jpg').write_bytes(request('/scene/preview', raw=True))
        hidden = request('/scenes/save', {'name':head['name'], 'scene_id':head['scene_id'],
                                         'expected_version':head['version']})
        assert {'object_id':str(target['id']), 'name':target['name']} in hidden['document']['hidden_environment']
        subprocess.run(['bash',str(ROOT/'scripts/restart_studio_bridge.sh')], cwd=ROOT, check=True)
        request('/scenes/history', {'scene_id':head['scene_id'],'expected_version':hidden['head']['version'],'direction':-1})
        (output/'undo-visible.jpg').write_bytes(request('/scene/preview', raw=True))
        request('/scenes/history', {'scene_id':head['scene_id'],'expected_version':head['version'],'direction':1})
        (output/'redo-hidden.jpg').write_bytes(request('/scene/preview', raw=True))
        from PIL import Image, ImageChops, ImageStat
        def difference(a,b):
            return sum(ImageStat.Stat(ImageChops.difference(Image.open(output/a), Image.open(output/b))).mean)/3
        delta = difference('visible.jpg','hidden.jpg')
        assert delta > .2, 'No observable visibility change'
        report = {'scene_id':head['scene_id'], 'object_id':str(target['id']),
                  'visible_hidden_pixel_delta':delta, 'history_across_bridge_restart':True,
                  'visual_review_required':True}
        (output/'report.json').write_text(json.dumps(report, indent=2))
        print(json.dumps(report), flush=True)
    finally:
        request('/scenes/restore', {'scene_id':head['scene_id'],'version':head['version']})


if __name__ == '__main__': main()

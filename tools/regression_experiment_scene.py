"""Opt-in native nonempty experiment snapshot -> scene -> restore regression."""
import json
import time
import uuid

from regression_scene_versions import ROOT, request


def main():
    assert request('system/preflight')['ready']
    owned = set()
    execution = None
    try:
        baseline = request('scenes/save', {'name':'验证：实验快照测试前基线'})
        previous_ids = {o['stable_id'] for o in baseline['document']['objects']}
        obj = request('objects/spawn', {'blueprint_id':'static.prop.advertisement',
            'transform':{'location':{'x':393.098,'y':-228.088,'z':2.5}}})['object']
        owned.add(obj['id'])
        request('collection/start', {'mode':'stationary','frames':10,'every':1,'max_frames':3})
        session = request('session/status')['session']
        execution = session['run_id']
        snapshot = session['configuration']['starting_scene']
        target = next(o for o in snapshot['objects']
                      if o['stable_id'] not in previous_ids and o['blueprint_id']=='static.prop.advertisement'
                      and abs(o['transform']['location']['x']-393.098)<.01)
        deadline = time.monotonic()+120
        while time.monotonic()<deadline:
            session = request('session/status')['session']
            assert session['run_id']==execution
            if session['state'] not in ('preparing','running','stopping','recovering'):
                break
            if session['state']=='recovering' and session.get('error'):
                raise RuntimeError(session['error'])
            time.sleep(.5)
        assert session['state']=='completed' and not session.get('error'), session
        assert session['configuration']['starting_scene']==snapshot
        saved = request('scenes/from-experiment', {'run_id':execution,'name':'验证：非空实验快照恢复'})
        assert saved['world_modified'] is False
        request('objects/delete', {'actor_id':obj['id']})
        owned.remove(obj['id'])
        restored = request('scenes/restore', {'scene_id':saved['head']['scene_id']})
        replacement = restored['bindings'][target['stable_id']]
        owned.add(replacement)
        assert replacement != obj['id']
        listing = request('catalog/objects?category=spawned_props&origin=user')['objects']
        actor = next(o for o in listing if o['id']==replacement)
        for axis in ('x','y','z'):
            assert abs(actor['location'][axis]-target['transform']['location'][axis])<.02
        report = {'execution_id':execution,'scene_id':saved['head']['scene_id'],
                  'stable_id':target['stable_id'],'before':obj['id'],'after':replacement,
                  'position':actor['location'],'passed':True}
        output = ROOT/'runs/validation'/('experiment-scene-'+uuid.uuid4().hex+'.json')
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(report,indent=2))
        print(json.dumps({**report,'report':str(output)}),flush=True)
    finally:
        session = request('session/status')['session']
        if execution and session['run_id']==execution and session['state'] in ('preparing','running','stopping'):
            request('collection/stop',{'run_id':execution})
            deadline = time.monotonic()+90
            while time.monotonic()<deadline:
                session = request('session/status')['session']
                if session['run_id']!=execution or session['state'] not in ('preparing','running','stopping','recovering'):
                    break
                time.sleep(.5)
            if session['state'] in ('preparing','running','stopping','recovering'):
                raise RuntimeError(f'World not ready for cleanup; test actors retained: {sorted(owned)}')
        for actor_id in owned:
            request('objects/delete',{'actor_id':actor_id})


if __name__=='__main__': main()

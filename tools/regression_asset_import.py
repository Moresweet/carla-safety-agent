"""Create a unique Blender asset, verify strict import and duplicate rejection."""
import json
import argparse
import time
import uuid
from pathlib import Path

import carla

from carla_safety_agent.world_health import observe_idle
from regression_material_slots import ROOT, request


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--require-first-material',action='store_true')
    parser.add_argument('--require-inherited-lock',action='store_true')
    parser.add_argument('--job-id',help='Reuse this explicitly selected exported job instead of generating a new asset')
    args=parser.parse_args()
    assert request('/system/preflight')['ready']
    assert request('/batches/scheduler')['scheduler']['state'] != 'running'
    session=request('/session/status')['session']['run_id']
    client=carla.Client('127.0.0.1',2000)
    client.set_timeout(10)
    world=client.get_world()
    before=observe_idle(client,world.get_map().name,seconds=1)
    camera=world.get_spectator().get_transform()
    name='ImportAudit_'+uuid.uuid4().hex[:16]
    output=ROOT/'runs/validation'/('asset-import-'+uuid.uuid4().hex)
    output.mkdir(parents=True,exist_ok=False)
    report={'state':'started','before':before,'name':name,
            'retained_assets':'Unique test source and registered Unreal asset remain traceable; no existing asset overwritten'}
    actor_id=None
    try:
        if args.job_id:
            import re
            assert re.fullmatch('[a-zA-Z0-9]{1,64}',args.job_id)
            generation=next(a for a in request('/blender/generations')['attempts'] if a['job_id']==args.job_id)
            assert generation['state']=='exported'
            asset={'job_id':args.job_id}
            report['generation']=generation
        else:
            asset=request('/blender/create',{'name':name,'shape':'cube','dimensions':[2,.4,.8],
                                           'color':[.1,.7,.2,1],'roughness':.45})
        report['job_id']=asset['job_id']
        (output/'report.json').write_text(json.dumps(report,indent=2))
        result=request('/blender/import',{'job_id':asset['job_id'],'name':name})
        report['import']=result
        assert result['import_returncode']==0 and result['blueprint_id']=='generated.prop.'+name.lower()
        attempts=request('/blender/imports')['attempts']
        assert next(a for a in attempts if a['attempt_id']==result['import_attempt_id'])['state']=='registered'
        if args.require_inherited_lock:
            assert next(a for a in attempts if a['attempt_id']==result['import_attempt_id'])['import_lock_inherited_by_child'] is True
            report['inherited_lock_launch_verified']=True
        import urllib.error
        try:
            request('/blender/import',{'job_id':asset['job_id'],'name':name})
        except urllib.error.HTTPError as exc:
            assert 'already registered' in exc.read().decode()
        else:
            raise AssertionError('Duplicate asset name accepted')
        attempts=[a for a in request('/blender/imports')['attempts'] if a['job_id']==asset['job_id']]
        assert {a['state'] for a in attempts}=={'registered','needs_attention'}
        report['duplicate_rejected']=True
        transform=world.get_map().get_spawn_points()[0]
        location=transform.location+transform.get_forward_vector()*8
        spawned=request('/blender/spawn',{'blueprint_id':result['blueprint_id'],
            'transform':{'location':{'x':location.x,'y':location.y,'z':location.z+1},
                         'rotation':{'yaw':transform.rotation.yaw},'snap_to_ground':True}})
        actor_id=spawned['object']['id']
        report['actor_id']=actor_id
        (output/'report.json').write_text(json.dumps(report,indent=2))
        request('/focus/actor',{'actor_id':actor_id})
        (output/'first-preview.jpg').write_bytes(request('/scene/preview',raw=True))
        time.sleep(3)
        (output/'settled-preview.jpg').write_bytes(request('/scene/preview',raw=True))
        if args.require_first_material:
            from PIL import Image
            counts=[]
            for filename in ('first-preview.jpg','settled-preview.jpg'):
                image=Image.open(output/filename).convert('RGB')
                w,h=image.size
                # Fixed-camera test fixture: target lies at the center, road
                # behind it is neutral. This is not a generic material oracle.
                pixels=image.crop((w//2-45,h//2-45,w//2+45,h//2+45)).getdata()
                counts.append(sum(g>70 and g>r*1.25 and g>b*1.15 for r,g,b in pixels))
            report['green_fixture_pixels_first_settled']=counts
            assert min(counts)>100 and counts[0]>=counts[1]*.5, 'First preview still lacks the requested fixture material'
        report.update(state='execution_verified',visual_review_required=True)
    except BaseException as exc:
        report.update(state='failed',error=str(exc))
        raise
    finally:
        try:
            assert request('/session/status')['session']['run_id']==session and client.get_world().id==before['episode']
            if actor_id is not None:
                request('/objects/delete',{'actor_id':actor_id})
            world.get_spectator().set_transform(camera)
            report['after']=observe_idle(client,before['map'])
        except BaseException as exc:
            report.update(state='recovery_failed',cleanup_error=str(exc))
            raise
        finally:
            (output/'report.json').write_text(json.dumps(report,indent=2))
            print(output,flush=True)


if __name__=='__main__':main()

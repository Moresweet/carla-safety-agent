"""Create a unique Blender asset, verify strict import and duplicate rejection."""
import json
import time
import uuid
from pathlib import Path

import carla

from carla_safety_agent.world_health import observe_idle
from regression_material_slots import ROOT, request


def main():
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
        asset=request('/blender/create',{'name':name,'shape':'cube','dimensions':[2,.4,.8],
                                       'color':[.1,.7,.2,1],'roughness':.45})
        report['job_id']=asset['job_id']
        (output/'report.json').write_text(json.dumps(report,indent=2))
        result=request('/blender/import',{'job_id':asset['job_id'],'name':name})
        report['import']=result
        assert result['import_returncode']==0 and result['blueprint_id']=='generated.prop.'+name.lower()
        attempts=request('/blender/imports')['attempts']
        assert next(a for a in attempts if a['attempt_id']==result['import_attempt_id'])['state']=='registered'
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

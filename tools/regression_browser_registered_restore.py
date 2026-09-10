"""Bounded browser source registration and confirmed native restore of one saved test object."""
import argparse
import json
from pathlib import Path
import subprocess
import time
import uuid
import carla
from regression_scene_versions import ROOT,request
from carla_safety_agent.scene_store import SceneStore
from carla_safety_agent.provenance import ActorProvenance
from carla_safety_agent.blender_pipeline import BlenderPipeline
from carla_safety_agent.world_health import observe_idle


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scene',required=True);parser.add_argument('--node',required=True)
    args=parser.parse_args()
    saved=SceneStore(ROOT/'data/scenes').read(args.scene)
    objects=saved['document']['objects']
    assert len(objects)==1 and objects[0]['blueprint_id'].startswith('generated.prop.')
    stable=objects[0]['stable_id']
    assert request('system/preflight')['ready']
    assert request('batches/scheduler')['scheduler']['state']!='running'
    client=carla.Client('127.0.0.1',2000);client.set_timeout(10);world=client.get_world()
    before=observe_idle(client,world.get_map().name,seconds=1)
    assert saved['document']['map']==before['map']
    session=request('session/status')['session']['run_id']
    baseline=request('scenes/save',{'name':'网页注册恢复前基线'})
    baseline_ids={obj['stable_id'] for obj in baseline['document']['objects']};assert stable not in baseline_ids
    output=ROOT/'runs/validation'/('browser-registered-restore-'+uuid.uuid4().hex);output.mkdir()
    report={'state':'started','before':before,'stable_id':stable}
    provenance=ActorProvenance(ROOT/'.runtime/actor-provenance.json')
    try:
        result=subprocess.run([args.node,str(ROOT/'tools/browser_reviewed_models.mjs'),
            '--bundle-scene',args.scene,'--bundle-sources','--bundle-register','--bundle-restore'],
            cwd=ROOT,capture_output=True,text=True,timeout=700)
        (output/'browser.log').write_text(result.stdout+'\n'+result.stderr)
        assert result.returncode==0,result.stderr[-3000:]
        browser=Path(json.loads(result.stdout.strip().splitlines()[-1])['output'])
        report['browser']=str(browser)
        registration=json.loads((browser/'bundle-registration-report.json').read_text())
        replacement=registration['registration']['blueprint_replacements'][objects[0]['blueprint_id']]
        world.wait_for_tick(5)
        live={actor.id:actor for actor in world.get_actors()}
        matches=[live[int(actor_id)] for actor_id,row in provenance.records(world.id).items()
                 if row.get('stable_id')==stable and int(actor_id) in live and row.get('type_id')==live[int(actor_id)].type_id]
        assert len(matches)==1;actor=matches[0]
        assert actor.attributes['mesh_path']==BlenderPipeline(ROOT).registry()[replacement]['mesh_path']
        request('focus/actor',{'actor_id':actor.id});time.sleep(.3)
        from regression_material_slots import request as raw_request
        (output/'restored-object.jpg').write_bytes(raw_request('/scene/preview',raw=True))
        report.update(state='verified',actor_id=actor.id,blueprint_id=replacement,
                      registered_bundle_id=registration['output_bundle_id'],mesh_path_verified=True)
    except BaseException as exc:report.update(state='failed',error=str(exc));raise
    finally:
        try:
            assert client.get_world().id==before['episode'] and request('session/status')['session']['run_id']==session,'World owner changed; inspect before cleanup'
            live={actor.id:actor for actor in world.get_actors()}
            for actor_id,row in provenance.records(world.id).items():
                if row.get('stable_id')==stable and int(actor_id) in live and row.get('type_id')==live[int(actor_id)].type_id:
                    request('objects/delete',{'actor_id':int(actor_id)})
            request('scenes/restore',{'scene_id':baseline['head']['scene_id'],'version':baseline['head']['version']})
            observed=request('scenes/save',{'name':'网页注册恢复清理后'})['document']
            assert {obj['stable_id'] for obj in observed['objects']}==baseline_ids
            report['after']=observe_idle(client,before['map']);report['test_actor_removed']=True
        except Exception as exc:report.update(state='recovery_failed',error=str(exc));raise
        finally:(output/'report.json').write_text(json.dumps(report,indent=2));print(output,flush=True)


if __name__=='__main__':main()

"""Own one test prop, restore it through real browser consent, then clean it up."""
import argparse
import json
import math
import subprocess
import time
import uuid
import urllib.request
import urllib.error
from pathlib import Path
import carla
from regression_scene_versions import ROOT,request
from carla_safety_agent.provenance import ActorProvenance
from carla_safety_agent.world_health import observe_idle


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--node',required=True)
    parser.add_argument('--vehicle-atlas',type=Path,help='Test a versioned Audi body texture instead of a prop')
    args=parser.parse_args()
    if args.vehicle_atlas:
        args.vehicle_atlas=args.vehicle_atlas.resolve()
        assert ROOT/'runs/validation' in args.vehicle_atlas.parents and args.vehicle_atlas.is_file()
    assert request('system/preflight')['ready']
    assert request('batches/scheduler')['scheduler']['state']!='running'
    session=request('session/status')['session']['run_id']
    client=carla.Client('127.0.0.1',2000);client.set_timeout(10)
    world=client.get_world();before=observe_idle(client,world.get_map().name,seconds=1)
    baseline=request('scenes/save',{'name':'浏览器包恢复测试前基线'})
    baseline_ids={obj['stable_id'] for obj in baseline['document']['objects']}
    output=ROOT/'runs/validation'/('browser-bundle-restore-'+uuid.uuid4().hex);output.mkdir()
    report={'state':'started','before':before};owned=set();stable=None
    try:
        pose={'location':{'x':393.098,'y':-228.088,'z':2.5}}
        if args.vehicle_atlas:
            spawn=world.get_map().get_spawn_points()[0]
            pose={'location':{'x':spawn.location.x,'y':spawn.location.y,'z':spawn.location.z+.5},
                  'rotation':{'yaw':spawn.rotation.yaw}}
        original=request('objects/spawn',{'blueprint_id':'vehicle.audi.a2' if args.vehicle_atlas else 'static.prop.advertisement',
            'transform':pose})['object']
        owned.add(original['id'])
        if args.vehicle_atlas:
            from regression_material_slots import request as raw_request
            applied=raw_request('/apply?actor_id='+str(original['id']),args.vehicle_atlas.read_bytes())
            assert applied['versionable'] is True
        saved=request('scenes/save',{'name':'浏览器恢复专用测试对象'})
        added=[obj for obj in saved['document']['objects'] if obj['stable_id'] not in baseline_ids]
        assert len(added)==1
        target=added[0];stable=target['stable_id']
        request('objects/delete',{'actor_id':original['id']});owned.remove(original['id'])
        result=subprocess.run([args.node,str(ROOT/'tools/browser_reviewed_models.mjs'),
            '--bundle-scene',saved['head']['scene_id'],'--bundle-restore'],cwd=ROOT,capture_output=True,text=True,timeout=180)
        (output/'browser.log').write_text(result.stdout+'\n'+result.stderr)
        assert result.returncode==0,result.stderr[-2000:]
        browser=json.loads(result.stdout.strip().splitlines()[-1]);report['browser']=browser['output']
        records=ActorProvenance(ROOT/'.runtime/actor-provenance.json').records(world.id)
        live={actor.id:actor for actor in world.get_actors()}
        restored=[live[int(actor_id)] for actor_id,row in records.items()
            if row.get('stable_id')==stable and int(actor_id) in live and live[int(actor_id)].type_id==row.get('type_id')]
        assert len(restored)==1
        actor=restored[0];owned.add(actor.id)
        assert actor.id!=original['id'] and actor.type_id==target['blueprint_id']
        location=actor.get_location()
        assert all(abs(getattr(location,key)-value)<.02 for key,value in target['transform']['location'].items())
        request('focus/actor',{'actor_id':actor.id})
        if args.vehicle_atlas:
            transform=actor.get_transform()
            center=carla.Location(**{key:getattr(actor.bounding_box.location,key) for key in ('x','y','z')})
            transform.transform(center)
            eye=center+transform.get_forward_vector()*4.5+transform.get_right_vector()*5+carla.Location(z=1.7)
            delta=center-eye
            world.get_spectator().set_transform(carla.Transform(eye,carla.Rotation(
                pitch=math.degrees(math.atan2(delta.z,math.hypot(delta.x,delta.y))),
                yaw=math.degrees(math.atan2(delta.y,delta.x)))))
            time.sleep(.5)
        with urllib.request.urlopen('http://127.0.0.1:8765/scene/preview',timeout=30) as response:
            (output/'restored-object.jpg').write_bytes(response.read())
        browser_report=json.loads((Path(browser['output'])/'bundle-report.json').read_text())
        selection={'bundle_id':browser_report['uploadedId'],'scene_id':saved['head']['scene_id'],'version':saved['head']['version']}
        review=request('projects/bundle/restore-preview',selection)
        if args.vehicle_atlas:
            assert review['actor_material_state_replaced'] and review['actor_material_count']>=1
            assert records[str(actor.id)]['actor_materials'][0]['texture']==applied['texture']
            report['restored_texture']=applied['texture']
        approval={'review_token':review['review_token'],'confirmed':True}
        camera=world.get_spectator().get_transform()
        ids={item.id for item in world.get_actors()}
        def rejected(expected):
            try:request('projects/bundle/restore-confirm',approval)
            except urllib.error.HTTPError as exc:
                assert exc.code==400
                assert expected in json.loads(exc.read())['error']
            else:raise AssertionError('Stale restore was accepted')
        try:
            changed=world.get_spectator().get_transform();changed.location.x+=.5
            world.get_spectator().set_transform(changed)
            rejected('Managed scene changed')
        finally:world.get_spectator().set_transform(camera)
        rejected('Unknown or already used')
        assert {item.id for item in world.get_actors()}==ids
        report.update(state='verified',stable_id=stable,original_actor=original['id'],restored_actor=actor.id,
                      stale_review_rejected=True,consumed_review_rejected=True)
    except BaseException as exc:
        report.update(state='failed',error=str(exc));raise
    finally:
        try:
            assert client.get_world().id==before['episode'] and request('session/status')['session']['run_id']==session,'World owner changed; manual recovery required'
            records=ActorProvenance(ROOT/'.runtime/actor-provenance.json').records(world.id)
            live={actor.id:actor for actor in world.get_actors()}
            if stable:
                owned.update(int(actor_id) for actor_id,row in records.items() if row.get('stable_id')==stable
                    and int(actor_id) in live and live[int(actor_id)].type_id==row.get('type_id'))
            for actor_id in owned:
                if actor_id in live:request('objects/delete',{'actor_id':actor_id})
            request('scenes/restore',{'scene_id':baseline['head']['scene_id'],'version':baseline['head']['version']})
            observed=request('scenes/save',{'name':'浏览器包恢复测试清理后'})['document']
            assert {obj['stable_id'] for obj in observed['objects']}==baseline_ids
            report['after']=observe_idle(client,before['map']);report['test_actor_removed']=True
        except Exception as exc:
            report.update(state='recovery_failed',error=str(exc));raise
        finally:
            (output/'report.json').write_text(json.dumps(report,indent=2));print(output,flush=True)


if __name__=='__main__':main()

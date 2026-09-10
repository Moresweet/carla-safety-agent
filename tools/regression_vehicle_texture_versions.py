"""Real Audi texture versions across restart and respawn, with an unrelated control."""
import argparse
import io
import json
import math
import subprocess
import time
import uuid
from pathlib import Path
from PIL import Image
import carla
from regression_material_slots import ROOT,request
from carla_safety_agent.provenance import ActorProvenance
from carla_safety_agent.project_bundle import export_bundle,read_bundle
from carla_safety_agent.world_health import observe_idle


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--atlas',type=Path,required=True)
    args=parser.parse_args();atlas=args.atlas.resolve()
    assert ROOT/'runs/validation' in atlas.parents and atlas.is_file()
    assert request('/system/preflight')['ready']
    assert request('/batches/scheduler')['scheduler']['state']!='running'
    session=request('/session/status')['session']['run_id']
    client=carla.Client('127.0.0.1',2000);client.set_timeout(10);world=client.get_world()
    before=observe_idle(client,world.get_map().name,seconds=1)
    baseline=request('/scenes/save',{'name':'车辆纹理版本实测前基线'})
    output=ROOT/'runs/validation'/('vehicle-texture-versions-'+uuid.uuid4().hex);output.mkdir()
    report={'state':'started','before':before};owned=set();stable_ids=set()
    provenance=ActorProvenance(ROOT/'.runtime/actor-provenance.json')
    def spawn(offset):
        transform=world.get_map().get_spawn_points()[0]
        location=transform.location+transform.get_right_vector()*offset
        result=request('/objects/spawn',{'blueprint_id':'vehicle.audi.a2','transform':{
            'location':{'x':location.x,'y':location.y,'z':location.z+.5},'rotation':{'yaw':transform.rotation.yaw}}})['object']
        owned.add(result['id'])
        record=provenance.records(world.id)[str(result['id'])];stable_ids.add(record['stable_id'])
        world.wait_for_tick(5)
        return world.get_actor(result['id']),record['stable_id']
    def photo(actor,name):
        transform=actor.get_transform();center=carla.Location(**{key:getattr(actor.bounding_box.location,key) for key in ('x','y','z')})
        transform.transform(center)
        eye=center+transform.get_forward_vector()*4.5+transform.get_right_vector()*5+carla.Location(z=1.7)
        delta=center-eye
        world.get_spectator().set_transform(carla.Transform(eye,carla.Rotation(
            pitch=math.degrees(math.atan2(delta.z,math.hypot(delta.x,delta.y))),yaw=math.degrees(math.atan2(delta.y,delta.x)))))
        time.sleep(.2);(output/name).write_bytes(request('/scene/preview',raw=True))
    try:
        target,stable=spawn(0)
        original=request('/scenes/save',{'name':'车辆纹理版本测试'})
        assert not original['document']['actor_materials']
        photo(target,'target-original.jpg')
        applied=request('/apply?actor_id='+str(target.id),atlas.read_bytes());assert applied['versionable'] is True
        painted=request('/scenes/save',{'name':'车辆纹理版本测试','scene_id':original['head']['scene_id'],
            'expected_version':original['head']['version']})
        assert painted['document']['actor_materials'][0]['texture']==applied['texture']
        control,control_stable=spawn(7)
        payload=io.BytesIO();Image.new('RGB',(2048,2048),(20,180,40)).save(payload,format='PNG')
        control_applied=request('/apply?actor_id='+str(control.id),payload.getvalue())
        subprocess.run(['bash',str(ROOT/'scripts/restart_studio_bridge.sh')],cwd=ROOT,check=True,capture_output=True,text=True)
        assert client.get_world().id==before['episode']
        scene=original['head']['scene_id']
        request('/scenes/history',{'scene_id':scene,'direction':-1,'expected_version':painted['head']['version']})
        assert provenance.records(world.id)[str(target.id)]['actor_materials']==[]
        assert provenance.records(world.id)[str(control.id)]['actor_materials'][0]['texture']==control_applied['texture']
        photo(target,'target-undo.jpg');photo(control,'control-after-undo.jpg')
        request('/scenes/history',{'scene_id':scene,'direction':1,'expected_version':original['head']['version']})
        assert provenance.records(world.id)[str(target.id)]['actor_materials'][0]['texture']==applied['texture']
        photo(target,'target-redo.jpg')
        old_id=target.id;request('/objects/delete',{'actor_id':old_id});owned.remove(old_id)
        restored=request('/scenes/restore',{'scene_id':scene,'version':painted['head']['version']})
        new_id=restored['bindings'][stable];owned.add(new_id)
        assert new_id!=old_id and restored['spawned']==1
        target=world.get_actor(new_id)
        assert provenance.records(world.id)[str(new_id)]['actor_materials'][0]['texture']==applied['texture']
        assert provenance.records(world.id)[str(control.id)]['actor_materials'][0]['texture']==control_applied['texture']
        photo(target,'target-respawned.jpg');photo(control,'control-after-respawn.jpg')
        package=output/'scene.zip';export_bundle(ROOT/'data/scenes',ROOT/'data',[scene],package)
        manifest,files=read_bundle(package)
        assert files['textures/'+applied['texture']+'.png']==(ROOT/'data/textures'/(applied['texture']+'.png')).read_bytes()
        assert 'textures/'+control_applied['texture']+'.png' not in files
        report.update(state='verified',scene_id=scene,stable_id=stable,original_actor=old_id,restored_actor=new_id,
            texture=applied['texture'],unrelated_control_preserved=control_stable,
            bundle_actor_material_slots=manifest['dependencies']['actor_material_slots'])
    except BaseException as exc:report.update(state='failed',error=str(exc));raise
    finally:
        try:
            assert client.get_world().id==before['episode'] and request('/session/status')['session']['run_id']==session
            live={actor.id:actor for actor in world.get_actors()}
            owned.update(int(actor_id) for actor_id,row in provenance.records(world.id).items()
                if row.get('stable_id') in stable_ids and int(actor_id) in live and row.get('type_id')==live[int(actor_id)].type_id)
            for actor_id in owned:
                if actor_id in live:request('/objects/delete',{'actor_id':actor_id})
            request('/scenes/restore',{'scene_id':baseline['head']['scene_id'],'version':baseline['head']['version']})
            report['after']=observe_idle(client,before['map']);report['owned_actors_removed']=True
        except Exception as exc:report.update(state='recovery_failed',cleanup_error=str(exc));raise
        finally:(output/'report.json').write_text(json.dumps(report,indent=2));print(output,flush=True)


if __name__=='__main__':main()

"""Explicit Town04/Town05 reviewed scene handoff on an empty local editor."""
import copy
import argparse
import json
import math
import subprocess
import time
import uuid
import urllib.error
import urllib.request

import carla
from regression_scene_versions import ROOT,request
from carla_safety_agent.scene_store import SceneStore,atomic
from carla_safety_agent.world_health import observe_idle


def wait_job(identity):
    deadline=time.monotonic()+180
    while time.monotonic()<deadline:
        row=request('scenes/handoff')
        assert row['request_id']==identity,'Map handoff ownership changed'
        if row['state']!='running':
            assert row['state']=='restored',row
            return row
        # Preflight must return a prompt, explicit gate without native RPCs.
        health=request('system/preflight')
        assert not health['ready'] or request('scenes/handoff')['state']=='restored'
        time.sleep(.3)
    raise TimeoutError('Map handoff still running; inspect without retrying')


def run_selection(head,node=None):
    if node:
        completed=subprocess.run([node,str(ROOT/'tools/browser_reviewed_models.mjs'),'--handoff-scene',head['scene_id']],
            cwd=ROOT,capture_output=True,text=True,timeout=240)
        assert completed.returncode==0,completed.stderr
        output=json.loads(completed.stdout.strip().splitlines()[-1])['output']
        row=json.loads((ROOT/output/'map-handoff-result.json').read_text())
        assert row['selection']=={key:head[key] for key in ('scene_id','version')}
        return {**row,'browser_output':output}
    selection={key:head[key] for key in ('scene_id','version')}
    review=request('scenes/handoff/preview',selection)
    assert not review['world_modified'] and review['source_map']!=review['target_map']
    row=request('scenes/handoff/confirm',{'review_token':review['review_token'],'confirmed':True})
    for path,payload in [('scenes/handoff/confirm',{'review_token':review['review_token'],'confirmed':True}),
                         ('objects/spawn',{'blueprint_id':'static.prop.box01','transform':{}})]:
        try:request(path,payload)
        except urllib.error.HTTPError as exc:assert exc.code==400
        else:raise AssertionError('Conflicting world operation accepted during map handoff')
    return wait_job(row['request_id'])


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--browser-node');parser.add_argument('--actor-texture');args=parser.parse_args()
    assert request('system/preflight')['ready']
    assert request('batches/scheduler')['scheduler']['state']!='running'
    original=request('scenes/save',{'name':'跨地图恢复验收前工作台'})
    source=original['document']
    assert source['map']=='Carla/Maps/Town04'
    assert not source['objects'] and not source.get('environment_materials') and not source.get('hidden_environment'), 'Do not discard user edits'
    # Position is from an existing real Town05 capture, not a guessed proxy map.
    folder=ROOT/'.runtime/generated-scenarios/capture-20260910T211256-dbb150cc'
    manifest=json.loads((folder/'manifest.json').read_text());assert manifest['map'].endswith('Town05')
    entries=json.loads((folder/'index.json').read_text())['frames']
    matrix=json.loads((folder/entries[10]['path']/'frame.json').read_text())['ego']['matrix']
    transform={'location':dict(zip(('x','y','z'),[matrix[i][3]+(.1 if i==2 else 0) for i in range(3)])),
               'rotation':{'pitch':0,'yaw':math.degrees(math.atan2(matrix[1][0],matrix[0][0])),'roll':0}}
    stable=uuid.uuid4().hex;target=copy.deepcopy(source)
    target.update(map='Carla/Maps/Town05',objects=[{'stable_id':stable,'blueprint_id':'vehicle.audi.a2',
        'transform':transform,'spawn_options':{}}])
    if args.actor_texture:
        from carla_safety_agent.material_library import MaterialLibrary
        MaterialLibrary(ROOT/'data').texture(args.actor_texture)
        target['actor_materials']=[{'stable_id':stable,'blueprint_id':'vehicle.audi.a2','component':'VehicleMesh',
            'slot':4,'texture':args.actor_texture}]
    saved=SceneStore(ROOT/'data/scenes').save(target,'跨地图验收 Town05 Audi')
    output=ROOT/'runs/validation'/('scene-handoff-'+uuid.uuid4().hex);output.mkdir()
    report={'state':'starting','original_scene':original['head'],'target_scene':saved['head'],'stable_id':stable,
        'scope':'Reviewed same-machine Town04/Town05 handoff; no engine crash or power-loss claim'}
    atomic(output/'report.json',report);print(output,flush=True)
    try:
        outward=run_selection(saved['head'],args.browser_node);report['outward']=outward;atomic(output/'report.json',report)
        actor_id=outward['bindings'][stable]
        client=carla.Client('127.0.0.1',2000);client.set_timeout(10);world=client.get_world()
        actor=world.get_actor(actor_id);assert actor and actor.type_id=='vehicle.audi.a2'
        assert abs(actor.get_location().x-transform['location']['x'])<.1
        if args.actor_texture:
            current=request('scenes/save',{'name':'跨地图恢复后的纹理证据'})['document']
            assert current['actor_materials']==target['actor_materials']
            report['actor_material_references_verified']=True;report['texture']=args.actor_texture
        pose=actor.get_transform();center=carla.Location(**{key:getattr(actor.bounding_box.location,key) for key in ('x','y','z')})
        pose.transform(center);eye=center+pose.get_forward_vector()*4.5+pose.get_right_vector()*5+carla.Location(z=1.7)
        delta=center-eye
        world.get_spectator().set_transform(carla.Transform(eye,carla.Rotation(
            pitch=math.degrees(math.atan2(delta.z,math.hypot(delta.x,delta.y))),yaw=math.degrees(math.atan2(delta.y,delta.x)))))
        with urllib.request.urlopen('http://127.0.0.1:8765/scene/preview',timeout=20) as response:
            (output/'town05-audi.jpg').write_bytes(response.read())
        inward=run_selection(original['head'],args.browser_node);report['inward']=inward
        report['health']=observe_idle(client,'Town04')
        restored=request('scenes/save',{'name':'跨地图验收返回状态'})['document']
        assert not restored['objects']
        for key in ('map','weather','environment_materials','hidden_environment'):
            assert restored.get(key)==source.get(key),key
        for group,values in source['spectator'].items():
            for key,value in values.items():assert abs(restored['spectator'][group][key]-value)<.001
        report['state']='verified';atomic(output/'report.json',report)
    except Exception as exc:
        report.update(state='failed',error=str(exc));atomic(output/'report.json',report)
        # Do not retry a destructive map load or auto-acknowledge uncertain state.
        raise
    print(output,flush=True)


if __name__=='__main__':main()

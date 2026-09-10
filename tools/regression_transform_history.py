"""Opt-in position history: two owned props, restart, GUI undo/redo and intent inspection."""
import argparse
import json
import subprocess
import uuid
import urllib.error
import carla
from regression_scene_versions import ROOT,request
from carla_safety_agent.transform_history import TransformHistory


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--node',required=True)
    args=parser.parse_args();assert request('system/preflight')['ready']
    client=carla.Client('127.0.0.1',2000);client.set_timeout(10);world=client.get_world()
    episode=world.id;camera=world.get_spectator().get_transform();owned=[]
    output=ROOT/'runs/validation'/('transform-history-'+uuid.uuid4().hex+'.json')
    report={'scope':'Owned idle prop history and deliberately unexecuted prepared intent; not an actual engine crash','episode':str(episode)}
    def status(actor):return request('objects/transform-history?actor_id='+str(actor))
    def move(actor,x):
        h=status(actor)
        return request('objects/update-reviewed',{'actor_id':actor,'transform':{'location':{'x':x}},'expected':h['observed']})
    def browser(*flags):
        result=subprocess.run([args.node,str(ROOT/'tools/browser_reviewed_models.mjs'),*flags],cwd=ROOT,text=True,capture_output=True,timeout=180)
        if result.returncode:raise RuntimeError(result.stdout+'\n'+result.stderr)
        value=json.loads(result.stdout.strip().splitlines()[-1]);print(json.dumps(value),flush=True);return value
    def restart():subprocess.run(['bash',str(ROOT/'scripts/restart_studio_bridge.sh')],cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
    try:
        for x in (393.098,403.098):
            owned.append(request('objects/spawn',{'blueprint_id':'static.prop.advertisement','transform':{'location':{'x':x,'y':-228.088,'z':2.5}}})['object']['id'])
        actor,control=owned;report.update(actor_id=actor,control_id=control)
        move(actor,394.098);move(actor,395.098);saved=status(actor)
        assert saved['undo_count']==2 and saved['redo_count']==0
        restart();assert status(actor)['revision']==saved['revision']
        try:request('objects/transform-history',{'action':'undo','confirmed':True,'expected':saved['observed'],'revision':'stale'})
        except urllib.error.HTTPError as exc:assert exc.code==400
        else:raise AssertionError('Stale history revision was accepted')
        assert abs(world.get_actor(actor).get_location().x-395.098)<.01
        report['browser_history']=browser('--transform-draft',str(actor),'--position-history')
        current=status(actor);assert current['undo_count']==3 and current['redo_count']==0
        assert abs(world.get_actor(control).get_location().x-403.098)<.01
        # Prepare an intent through the production store but deliberately do not
        # issue its native RPC. Restart must not assume it happened or retry it.
        store=TransformHistory(ROOT/'data/transform-history');identity=current['identity']
        pose=world.get_actor(actor).get_transform()
        source={'location':{k:float(getattr(pose.location,k)) for k in ('x','y','z')},
                'rotation':{k:float(getattr(pose.rotation,k)) for k in ('pitch','yaw','roll')}}
        target=json.loads(json.dumps(source));target['location']['x']+=.5
        prepared=store.begin(identity,'record',source,target);restart()
        pending=status(actor);assert pending['pending']['id']==prepared['pending']['id']
        try:move(actor,source['location']['x']+1)
        except urllib.error.HTTPError as exc:assert exc.code==400 and 'inspection' in json.load(exc)['error']
        else:raise AssertionError('Pending history did not gate further recorded moves')
        report['browser_inspection']=browser('--inspect-position-history',str(actor))
        cleared=status(actor);assert not cleared['pending'] and cleared['undo_count']==cleared['redo_count']==0
        assert abs(world.get_actor(actor).get_location().x-source['location']['x'])<.01
        assert (store.folder(identity)/(prepared['revision']+'.json')).is_file()
        assert abs(world.get_actor(control).get_location().x-403.098)<.01
        assert not world.get_settings().synchronous_mode and not list(world.get_actors().filter('sensor.*'))
        report.update(passed=True,restart_history_preserved=True,unrelated_actor_unchanged=True,prepared_intent_not_replayed=True,
            inspection_archive=str(store.folder(identity)/(prepared['revision']+'.json')))
    except Exception as exc:
        report.update(passed=False,error=str(exc));raise
    finally:
        if client.get_world().id==episode:
            for actor in owned:request('objects/delete',{'actor_id':actor})
            world.get_spectator().set_transform(camera)
            report['fixtures_cleaned']=True
        output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2))
        print(json.dumps({'report':str(output),'passed':report.get('passed',False)}),flush=True)


if __name__=='__main__':main()

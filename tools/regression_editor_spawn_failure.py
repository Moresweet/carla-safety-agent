"""Real editor spawns with controlled post-spawn faults; never kills the simulator."""
import ast
import json
import uuid
from types import SimpleNamespace as NS
import carla
from regression_scene_versions import ROOT,request
from carla_safety_agent.provenance import ActorProvenance
from carla_safety_agent.world_health import observe_idle


def main():
    assert request('system/preflight')['ready']
    assert request('batches/scheduler')['scheduler']['state']!='running'
    session=request('session/status')['session']['run_id']
    client=carla.Client('127.0.0.1',2000);client.set_timeout(10)
    world=client.get_world();before=observe_idle(client,world.get_map().name,seconds=1)
    provenance=ActorProvenance(ROOT/'.runtime/actor-provenance.json')
    tree=ast.parse((ROOT/'tools/livery_bridge.py').read_text())
    source=ast.Module(body=[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='_spawn_editor_object'],type_ignores=[])
    assert len(source.body)==1
    owned=[];rows=[];error=None
    output=ROOT/'runs/validation'/('editor-spawn-failure-'+uuid.uuid4().hex+'.json')
    try:
        for failure in ('mark','velocity'):
            class Actor:
                def __init__(self,actor):self.actor=actor
                def __getattr__(self,name):return getattr(self.actor,name)
                def set_autopilot(self,*_):raise AssertionError('Unexpected Traffic Manager access')
                def set_target_velocity(self,*_):raise RuntimeError('controlled velocity failure')
            class World:
                def __getattr__(self,name):return getattr(world,name)
                def spawn_actor(self,*args):
                    actor=world.spawn_actor(*args);owned.append(actor);return Actor(actor)
            def mark(*args):
                if failure=='mark':raise RuntimeError('controlled mark failure')
                return provenance.mark(*args)
            env={'connect_world':lambda:World(),'_provenance':NS(records=provenance.records,mark=mark,bind=provenance.bind),
                 'BLENDER':NS(registry=lambda:{}),'carla':carla,'hero_actor':lambda _:True,'_carla_client':client,
                 '_editor_actors':set(),'_actor_object_names':{},'_generated_actor_assets':{}}
            exec(compile(source,str(ROOT/'tools/livery_bridge.py'),'exec'),env)
            transform=world.get_map().get_spawn_points()[0]
            try:
                env['_spawn_editor_object']('vehicle.audi.a2',{'location':{
                    'x':transform.location.x,'y':transform.location.y,'z':transform.location.z+2}})
            except RuntimeError as exc:assert str(exc)=='controlled '+failure+' failure',str(exc)
            else:raise AssertionError('Controlled fault did not occur')
            assert owned and world.get_snapshot().find(owned[-1].id) is None
            assert not env['_editor_actors'] and not env['_actor_object_names']
            rows.append({'fault':failure,'actor_id':owned[-1].id,'native_actor_removed':True})
    except BaseException as exc:
        error=str(exc);raise
    finally:
        assert client.get_world().id==before['episode'] and request('session/status')['session']['run_id']==session
        if owned:
            replies=client.apply_batch_sync([carla.command.DestroyActor(actor.id) for actor in owned],False)
            assert len(replies)==len(owned)
            assert all(not reply.error or reply.error=='unable to destroy actor: not found' for reply in replies)
            snapshot=world.wait_for_tick(5)
            assert all(snapshot.find(actor.id) is None for actor in owned)
        after=observe_idle(client,before['map'])
        output.write_text(json.dumps({'state':'failed' if error else 'verified','error':error,'before':before,'probes':rows,'after':after,
            'scope':'Real spawns and cleanup with injected Python faults; not an actual disk outage or native crash'},indent=2))
        print(output,flush=True)


if __name__=='__main__':main()

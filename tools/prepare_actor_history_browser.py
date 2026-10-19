"""Prepare one owned actor for explicit browser verification; receipt is cleanup identity."""
import json
import uuid
import argparse
from types import SimpleNamespace
import carla
from cleanup_superseded_model_captures import idle
from regression_material_slots import ROOT,request

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--failure',action='store_true');args=parser.parse_args()
    idle();assert request('/system/preflight')['ready']
    client=carla.Client('127.0.0.1',2000);client.set_timeout(5)
    world=client.get_world();pose=world.get_map().get_spawn_points()[0]
    folder=ROOT/'runs/validation'/('actor-history-browser-'+uuid.uuid4().hex);folder.mkdir()
    actor=request('/objects/spawn',{'blueprint_id':'walker.pedestrian.0001','transform':{'location':{'x':pose.location.x,'y':pose.location.y,'z':pose.location.z+.5}}})['object']
    receipt={'actor':actor,'episode':str(world.id),'state':'prepared'}
    (folder/'receipt.json').write_text(json.dumps(receipt,indent=2))
    try:
        atlas=ROOT/'runs/validation/browser-models-1717a51b-2f50-4fcc-be68-76ab4d9935f1/pedestrian-atlas.png'
        receipt['applied']=request('/apply/pedestrian?actor_id='+str(actor['id']),atlas.read_bytes())
        if args.failure:
            from carla_safety_agent.actor_material_history import ActorMaterialHistory,apply_with_history
            history=ActorMaterialHistory(ROOT/'data/actor-material-history')
            op=receipt['applied']['history_operation_id'];row=history.read(op)
            request('/materials/actor-history',dict(operation_id=op,revision=op,direction='undo',confirmed=True))
            previous=set(history.root.glob('*.json'))
            reapplied=request('/apply/pedestrian?actor_id='+str(actor['id']),atlas.read_bytes())
            assert reapplied['texture']==receipt['applied']['texture']
            def apply():
                raise RuntimeError('Browser fixture: synthetic uncertain journal after separate HTTP application')
            def rollback():raise RuntimeError('Browser fixture: rollback unavailable')
            try:apply_with_history(history.root,row['identity'],None,receipt['applied']['texture'],SimpleNamespace(apply=apply,rollback=rollback))
            except RuntimeError as error:assert 'requires inspection' in str(error)
            else:raise AssertionError('Failure fixture did not fail')
            receipt['failed']=next(history.read(p.stem) for p in set(history.root.glob('*.json'))-previous if history.read(p.stem)['state']=='needs_attention')
            receipt['failure_scope']='Synthetic uncertain journal after separately acknowledged native write; not a native transaction interruption'
        (folder/'receipt.json').write_text(json.dumps(receipt,indent=2))
    except Exception:
        request('/objects/delete',{'actor_id':actor['id']});raise
    print(json.dumps({'folder':str(folder),**receipt}))

if __name__=='__main__':main()

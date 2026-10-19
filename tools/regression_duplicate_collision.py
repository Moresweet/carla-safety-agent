"""Occupy first duplicate candidate; verify one alternative spawn and cleanup."""
import json
import uuid
import argparse
import time
from urllib.error import HTTPError
import carla
from regression_scene_versions import ROOT, request
from cleanup_superseded_model_captures import idle
from carla_safety_agent.copy_history import CopyHistory


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--undo',action='store_true',help='Also verify guarded copy undo and duplicate submission rejection')
    parser.add_argument('--redo',action='store_true',help='Verify redo and a second undo; implies --undo')
    args=parser.parse_args()
    if args.redo:args.undo=True
    idle();assert request('system/preflight')['ready']
    client=carla.Client('127.0.0.1',2000);client.set_timeout(5)
    world=client.get_world();owned=set();report={'passed':False}
    output=ROOT/'runs/validation'/('duplicate-collision-'+uuid.uuid4().hex+'.json')
    def spawn(pose):
        row=request('objects/spawn',{'blueprint_id':'vehicle.audi.a2','transform':{
            'location':dict(x=pose.location.x,y=pose.location.y,z=pose.location.z),
            'rotation':dict(pitch=pose.rotation.pitch,yaw=pose.rotation.yaw,roll=pose.rotation.roll)}})['object']
        owned.add(row['id']);world.wait_for_tick(5)
        return world.get_actor(row['id'])
    try:
        pose=world.get_map().get_spawn_points()[0];pose.location.z+=.5
        source=spawn(pose);pose=source.get_transform()
        blocked=pose.location+pose.get_right_vector()*(source.bounding_box.extent.y*2+2)
        blocker=spawn(carla.Transform(blocked,pose.rotation))
        before={a.id for a in world.get_actors()}
        response=request('objects/duplicate',{'actor_id':source.id})
        result=response['object'];owned.add(result['id'])
        operation=response['copy_operation_id']
        journal=CopyHistory(ROOT/'data/copy-history').read(operation)
        assert journal['state']=='confirmed'
        assert journal['identity']['actor_id']==source.id
        assert journal['target']['actor_id']==result['id']
        assert journal['identity']['stable_id']!=journal['target']['stable_id']
        listing=request('objects/edit-history?limit=200')
        assert next(row for row in listing['entries'] if row['operation_id']==operation)==journal
        world.wait_for_tick(5)
        after={a.id for a in world.get_actors()}
        assert after-before=={result['id']},'Expected exactly one newly created actor'
        expected=pose.location-pose.get_right_vector()*(source.bounding_box.extent.y*2+2)
        actual=world.get_actor(result['id']).get_location()
        assert actual.distance(expected)<.05,'Second candidate was not used'
        assert world.get_actor(blocker.id) is not None and world.get_actor(source.id) is not None
        if args.undo:
            target=world.get_actor(result['id']);current=target.get_transform()
            review=dict(episode=str(world.id),actor_id=target.id,type_id=target.type_id,
                location=dict(x=current.location.x,y=current.location.y,z=current.location.z),yaw=current.rotation.yaw)
            payload=dict(operation_id=operation,review=review,confirmed=True)
            before_journal=(ROOT/'data/copy-history'/f'{operation}.json').read_bytes()
            try:
                request('objects/copy-undo',{**payload,'review':{**review,'location':{**review['location'],'x':current.location.x+5}}})
                raise AssertionError('Stale pose was accepted')
            except HTTPError as error:
                assert error.code==400
                report['stale_pose_rejection']=json.load(error)
            assert world.get_actor(target.id) is not None
            assert (ROOT/'data/copy-history'/f'{operation}.json').read_bytes()==before_journal
            undone=request('objects/copy-undo',payload)
            assert undone['ok'] and undone['deletion']['backup']['stable_id']==journal['target']['stable_id']
            report['undo_response']=undone
            owned.remove(target.id)
            # Independent client snapshots may lag the bridge's confirmed deletion.
            # Bound observation, never resend deletion merely because a tick is stale.
            deadline=time.monotonic()+5
            observed=[]
            while True:
                snapshot=world.wait_for_tick(max(.1,deadline-time.monotonic()))
                present=snapshot.find(target.id) is not None or target.id in {a.id for a in world.get_actors()}
                observed.append({'frame':snapshot.frame,'target_present':present,
                                 'cached_lookup_present':world.get_actor(target.id) is not None})
                if not present:break
                if time.monotonic()>=deadline:raise AssertionError('Target still present after bounded observation')
            report['undo_observation']=observed
            assert world.get_actor(source.id) is not None and world.get_actor(blocker.id) is not None
            journal_after=CopyHistory(ROOT/'data/copy-history').read(operation)
            assert journal_after['undo']['state']=='confirmed'
            try:
                request('objects/copy-undo',payload)
                raise AssertionError('Duplicate undo was accepted')
            except HTTPError as error:
                assert error.code==400
                report['duplicate_undo_rejection']=json.load(error)
            assert CopyHistory(ROOT/'data/copy-history').read(operation)==journal_after
            report.update(undo=undone,undo_journal=journal_after,source_and_blocker_preserved=True)
            if args.redo:
                redo_payload=dict(operation_id=operation,deletion_id=undone['deletion']['operation_id'],confirmed=True)
                redone=request('objects/copy-redo',redo_payload)
                restored=redone['target'];owned.add(restored['actor_id'])
                assert restored['stable_id']==journal['target']['stable_id']
                assert restored['actor_id']!=target.id
                snapshot=world.wait_for_tick(5)
                assert snapshot.find(restored['actor_id']) is not None
                assert snapshot.find(source.id) is not None and snapshot.find(blocker.id) is not None
                current_row=CopyHistory(ROOT/'data/copy-history').read(operation)
                assert current_row['target']==restored and len(current_row['cycles'])==1 and 'undo' not in current_row
                try:
                    request('objects/copy-redo',redo_payload)
                    raise AssertionError('Duplicate redo was accepted')
                except HTTPError as error:
                    assert error.code==400
                    report['duplicate_redo_rejection']=json.load(error)
                actor=world.get_actor(restored['actor_id']);pose2=actor.get_transform()
                review2=dict(episode=str(world.id),actor_id=actor.id,type_id=actor.type_id,
                    location=dict(x=pose2.location.x,y=pose2.location.y,z=pose2.location.z),yaw=pose2.rotation.yaw)
                second=request('objects/copy-undo',dict(operation_id=operation,review=review2,confirmed=True))
                owned.remove(actor.id)
                snapshot=world.wait_for_tick(5)
                assert snapshot.find(actor.id) is None
                assert snapshot.find(source.id) is not None and snapshot.find(blocker.id) is not None
                final_row=CopyHistory(ROOT/'data/copy-history').read(operation)
                assert final_row['undo']['deletion']['actor_id']==actor.id and len(final_row['cycles'])==1
                report.update(redo=redone,second_undo=second,final_journal=final_row)
        report.update(passed=True,source=source.id,blocker=blocker.id,duplicate=result,
                      second_candidate_verified=True,new_actor_ids=sorted(after-before),
                      copy_journal=journal,history_api_verified=True)
    finally:
        report['cleanup']=[]
        for actor_id in owned:
            try:report['cleanup'].append(request('objects/delete',{'actor_id':actor_id}))
            except Exception as error:
                report['passed']=False;report['cleanup'].append({'actor_id':actor_id,'error':str(error)})
        output.write_text(json.dumps(report,indent=2))
        print(json.dumps({'receipt':str(output),'passed':report['passed']}))
    if not report['passed']:raise RuntimeError('Collision regression or cleanup failed')


if __name__=='__main__':main()

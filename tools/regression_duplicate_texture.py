"""Real supported actor material copy; keep visual evidence and clean owned actors."""
import argparse
import json
import math
import time
import uuid
import carla
from regression_material_slots import ROOT, request
from cleanup_superseded_model_captures import idle
from carla_safety_agent.provenance import ActorProvenance


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pedestrian',action='store_true')
    parser.add_argument('--redo',action='store_true',help='Undo and restore the textured duplicate before visual capture')
    parser.add_argument('--material-history',action='store_true',help='Undo and redo original texture via actor material HTTP history')
    parser.add_argument('--material-recovery',action='store_true',help='Controlled post-HTTP failure and explicit source recovery; requires material-history')
    args=parser.parse_args()
    if args.material_recovery and not args.material_history:parser.error('--material-recovery requires --material-history')
    blueprint='walker.pedestrian.0001' if args.pedestrian else 'vehicle.audi.a2'
    idle();assert request('/system/preflight')['ready']
    output=ROOT/'runs/validation'/('duplicate-texture-'+uuid.uuid4().hex);output.mkdir()
    client=carla.Client('127.0.0.1',2000);client.set_timeout(5)
    world=client.get_world();camera=world.get_spectator().get_transform()
    report={'passed':False,'blueprint':blueprint,'visual_review':'pending'};owned=set()
    provenance=ActorProvenance(ROOT/'.runtime/actor-provenance.json')
    try:
        pose=world.get_map().get_spawn_points()[0]
        original=request('/objects/spawn',{'blueprint_id':blueprint,'transform':{
            'location':{'x':pose.location.x,'y':pose.location.y,'z':pose.location.z+.5},
            'rotation':{'yaw':pose.rotation.yaw}}})['object'];owned.add(original['id'])
        atlas=ROOT/'runs/validation/browser-models-d2e6e1a0-ee47-4f88-b694-838d36e32789/vehicle-atlas.png'
        if args.pedestrian:
            atlas=ROOT/'runs/validation/browser-models-1717a51b-2f50-4fcc-be68-76ab4d9935f1/pedestrian-atlas.png'
        endpoint='/apply/pedestrian?actor_id=' if args.pedestrian else '/apply?actor_id='
        applied=request(endpoint+str(original['id']),atlas.read_bytes())
        assert applied['versionable'] is True
        before=provenance.records(world.id)[str(original['id'])]
        history_id=applied['history_operation_id']
        history=request('/objects/edit-history?limit=200')
        logged=next(row for row in history['entries'] if row['operation_id']==history_id)
        assert logged['kind']=='actor-material' and logged['state']=='confirmed'
        assert logged['identity']['stable_id']==before['stable_id']
        assert logged['identity']['actor_id']==original['id']
        assert logged['identity']['blueprint_id']==blueprint
        assert logged['before'] is None and logged['after']==applied['texture']
        assert logged['undo_supported'] is False
        report['material_history']=logged
        if args.material_history:
            journal_path=ROOT/'data/actor-material-history'/(history_id+'.json')
            def inspect_registered(expected,label):
                journal_before=journal_path.read_bytes()
                result=request('/materials/actor-history-inspection?operation_id='+history_id)
                assert result['operation_id']==history_id and result['identity']==logged['identity']
                assert result['registered_texture']==expected
                assert result['registry_matches']==label
                assert result['native_verified'] is False and result['automatic_retry_allowed'] is False
                assert journal_path.read_bytes()==journal_before
                report.setdefault('inspections',[]).append(result)
            inspect_registered(applied['texture'],'target')
            native=world.get_actor(original['id']);pose=native.get_transform()
            center=carla.Location(x=native.bounding_box.location.x,y=native.bounding_box.location.y,z=native.bounding_box.location.z)
            pose.transform(center)
            eye=(center+pose.get_forward_vector()*2+pose.get_right_vector()*-.8+carla.Location(z=.2)
                 if args.pedestrian else center+pose.get_forward_vector()*1.2+pose.get_right_vector()*-3.8+carla.Location(z=1.2))
            delta=center-eye
            world.get_spectator().set_transform(carla.Transform(eye,carla.Rotation(
                pitch=math.degrees(math.atan2(delta.z,math.hypot(delta.x,delta.y))),
                yaw=math.degrees(math.atan2(delta.y,delta.x)))))
            def capture_material(label):
                time.sleep(.3)
                (output/(label+'.jpg')).write_bytes(request('/scene/preview',raw=True))
            capture_material('material-applied')
            undone_material=request('/materials/actor-history',dict(operation_id=history_id,revision=history_id,direction='undo',confirmed=True))
            assert undone_material['applied'] is False
            assert provenance.records(world.id)[str(original['id'])].get('actor_materials',[])==[]
            inspect_registered(None,'source')
            capture_material('material-undone')
            import urllib.error
            try:
                request('/materials/actor-history',dict(operation_id=history_id,revision=history_id,direction='redo',confirmed=True))
            except urllib.error.HTTPError as error:
                assert error.code==400
            else:raise AssertionError('Stale revision accepted')
            redone_material=request('/materials/actor-history',dict(operation_id=history_id,revision=undone_material['revision'],direction='redo',confirmed=True))
            assert redone_material['applied'] is True
            assert provenance.records(world.id)[str(original['id'])]==before
            inspect_registered(applied['texture'],'target')
            capture_material('material-redone')
            report.update(material_undo=undone_material,material_redo=redone_material,stale_material_revision_rejected=True)
            if args.material_recovery:
                from types import SimpleNamespace
                from carla_safety_agent.actor_material_history import ActorMaterialHistory,apply_with_history
                history=ActorMaterialHistory(ROOT/'data/actor-material-history')
                restored=request('/materials/actor-history',dict(operation_id=history_id,revision=redone_material['revision'],direction='undo',confirmed=True))
                baseline=set(history.root.glob('*.json'))
                result=request(endpoint+str(original['id']),atlas.read_bytes())
                assert result['texture']==applied['texture']
                def injected():
                    raise RuntimeError('Synthetic uncertain journal after separate acknowledged HTTP application')
                def rollback_failure():raise RuntimeError('Controlled rollback failure to retain recovery fixture')
                try:apply_with_history(history.root,logged['identity'],None,applied['texture'],SimpleNamespace(apply=injected,rollback=rollback_failure))
                except RuntimeError as error:assert 'requires inspection' in str(error)
                else:raise AssertionError('Expected injected failure')
                failed=next(history.read(p.stem) for p in set(history.root.glob('*.json'))-baseline if history.read(p.stem)['state']=='needs_attention')
                failed_bytes=history.path(failed['operation_id']).read_bytes()
                try:request(endpoint+str(original['id']),atlas.read_bytes())
                except urllib.error.HTTPError as error:
                    assert error.code==400
                    report['unresolved_edit_rejection']=json.load(error)
                else:raise AssertionError('Unresolved actor slot accepted a new edit')
                assert history.path(failed['operation_id']).read_bytes()==failed_bytes
                try:
                    request('/materials/actor-history',dict(operation_id=result['history_operation_id'],
                        revision=result['history_operation_id'],direction='undo',confirmed=True))
                except urllib.error.HTTPError as error:
                    assert error.code==400
                    report['unresolved_old_undo_rejection']=json.load(error)
                else:raise AssertionError('Old undo bypassed unresolved actor slot')
                inspection=request('/materials/actor-history-inspection?operation_id='+failed['operation_id'])
                assert inspection['registry_matches']=='target'
                capture_material('recovery-before')
                payload=dict(operation_id=failed['operation_id'],inspection_token=inspection['inspection_token'],choice='source',registered_texture=inspection['registered_texture'],confirmed=True)
                recovery=request('/materials/actor-history-recover',payload)
                assert recovery['recovery']['state']=='confirmed'
                final=history.read(failed['operation_id'])
                assert final['state']==failed['state'] and final['error']==failed['error']
                assert provenance.records(world.id)[str(original['id'])].get('actor_materials',[])==[]
                capture_material('recovery-after')
                try:request('/materials/actor-history-recover',payload)
                except urllib.error.HTTPError as error:assert error.code==400
                else:raise AssertionError('Repeated recovery accepted')
                report.update(recovery_scope='Synthetic uncertain journal after separate real HTTP write; not interrupted native transaction or simulator crash',injected_failure=failed,recovery=recovery)
                # Continue the original copy check with its expected texture.
                request(endpoint+str(original['id']),atlas.read_bytes())
                assert provenance.records(world.id)[str(original['id'])]==before
        copied=request('/objects/duplicate',{'actor_id':original['id']})
        duplicate=copied['object'];owned.add(duplicate['id'])
        world.wait_for_tick(5)
        after=provenance.records(world.id)
        new=after[str(duplicate['id'])]
        assert new['stable_id']!=before['stable_id']
        assert after[str(original['id'])]==before
        assert new['actor_materials']==[{**row,'stable_id':new['stable_id']} for row in before['actor_materials']]
        if args.redo:
            native=world.get_actor(duplicate['id']);current=native.get_transform()
            review=dict(episode=str(world.id),actor_id=native.id,type_id=native.type_id,
                location=dict(x=current.location.x,y=current.location.y,z=current.location.z),yaw=current.rotation.yaw)
            undone=request('/objects/copy-undo',dict(operation_id=copied['copy_operation_id'],review=review,confirmed=True))
            owned.remove(duplicate['id'])
            restored=request('/objects/copy-redo',dict(operation_id=copied['copy_operation_id'],
                deletion_id=undone['deletion']['operation_id'],confirmed=True))
            restored_id=restored['target']['actor_id'];owned.add(restored_id)
            world.wait_for_tick(5)
            restored_record=provenance.records(world.id)[str(restored_id)]
            assert restored_id!=duplicate['id']
            assert restored_record['stable_id']==new['stable_id']
            assert restored_record['actor_materials']==new['actor_materials']
            assert provenance.records(world.id)[str(original['id'])]==before
            report.update(copy_operation_id=copied['copy_operation_id'],undo=undone,redo=restored,
                          pre_undo_duplicate=duplicate,restored_record=restored_record)
            duplicate={**duplicate,'id':restored_id}
        for label,actor in [('source',original),('duplicate',duplicate)]:
            native=world.get_actor(actor['id']);pose=native.get_transform()
            center=carla.Location(x=native.bounding_box.location.x,y=native.bounding_box.location.y,z=native.bounding_box.location.z)
            pose.transform(center)
            eye=(center+pose.get_forward_vector()*2+pose.get_right_vector()*-.8+carla.Location(z=.2)
                 if args.pedestrian else center+pose.get_forward_vector()*1.2+pose.get_right_vector()*-3.8+carla.Location(z=1.2))
            delta=center-eye
            world.get_spectator().set_transform(carla.Transform(eye,carla.Rotation(
                pitch=math.degrees(math.atan2(delta.z,math.hypot(delta.x,delta.y))),
                yaw=math.degrees(math.atan2(delta.y,delta.x)))))
            time.sleep(.3)
            (output/(label+'.jpg')).write_bytes(request('/scene/preview',raw=True))
        report.update(passed=True,source=original,duplicate=duplicate,source_record=before,
                      duplicate_record=new,texture=applied['texture'])
    finally:
        report['cleanup']=[]
        for actor_id in owned:
            try:report['cleanup'].append(request('/objects/delete',{'actor_id':actor_id}))
            except Exception as error:
                report['passed']=False;report['cleanup'].append({'actor_id':actor_id,'error':str(error)})
        try:
            if client.get_world().id!=world.id:raise RuntimeError('World changed; do not restore old spectator')
            world.get_spectator().set_transform(camera)
        except Exception as error:report['passed']=False;report['camera_cleanup_error']=str(error)
        (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print(json.dumps({'output':str(output),'passed':report['passed']}))
    if not report['passed']:raise RuntimeError('Texture duplication or cleanup failed')


if __name__=='__main__':main()

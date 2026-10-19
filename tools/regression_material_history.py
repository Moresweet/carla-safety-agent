"""Two distinct slot textures, guarded undo/redo, exact cleanup and screenshots."""
import io
import argparse
import json
import uuid
import urllib.parse
from urllib.error import HTTPError
import carla
from PIL import Image
from regression_material_slots import ROOT, request
from cleanup_superseded_model_captures import idle


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--concurrent',action='store_true')
    parser.add_argument('--recovery',action='store_true',help='Inject a post-application callback failure, then explicitly restore the source')
    args=parser.parse_args()
    idle();assert request('/system/preflight')['ready']
    output=ROOT/'runs/validation'/('material-history-'+uuid.uuid4().hex);output.mkdir()
    client=carla.Client('127.0.0.1',2000);client.set_timeout(5)
    world=client.get_world();spectator=world.get_spectator();camera=spectator.get_transform()
    target='SM_Church01_5'
    objects=request('/catalog/objects?'+urllib.parse.urlencode(dict(category='buildings',q=target,limit=200)))['objects']
    obj=next(o for o in objects if o['name'] in (target,target+'_SM_0',target+'_SM'))
    selection=dict(object_id=str(obj['id']),component='StaticMeshComponent0',slot=0)
    assert not request('/materials/catalog?object_id='+selection['object_id'])['overrides'],'Preserve existing user edits'
    report={'passed':False};attempted=False
    def capture(name):
        world.wait_for_tick(5)
        (output/(name+'.jpg')).write_bytes(request('/scene/preview',raw=True))
    def digest():
        edits=request('/materials/catalog?object_id='+selection['object_id'])['overrides']
        return next((e['texture'] for e in edits if e['component']==selection['component'] and e['slot']==0),None)
    try:
        request('/focus/environment',{'object_id':selection['object_id']});capture('before')
        applied=[]
        for label,color in [('a',(0,220,220)),('b',(220,0,220))]:
            payload=io.BytesIO();Image.new('RGB',(1024,1024),color).save(payload,format='PNG')
            attempted=True
            result=request('/materials/apply?'+urllib.parse.urlencode(selection),payload.getvalue())
            applied.append(result);assert digest()==result['texture'];capture(label)
        assert applied[0]['texture']!=applied[1]['texture']
        operation=applied[1]['material_operation_id']
        payload=dict(operation_id=operation,direction='undo',revision=operation,confirmed=True)
        if args.concurrent:
            from concurrent.futures import ThreadPoolExecutor
            from threading import Barrier
            from carla_safety_agent.material_history import MaterialHistory
            barrier=Barrier(2)
            def submit():
                barrier.wait(timeout=5)
                try:return {'status':200,'body':request('/materials/history',payload)}
                except HTTPError as error:return {'status':error.code,'body':json.load(error)}
            with ThreadPoolExecutor(max_workers=2) as pool:
                responses=list(pool.map(lambda _:submit(),range(2)))
            report['concurrent_responses']=responses
            assert sorted(r['status'] for r in responses)==[200,400]
            undo=next(r['body'] for r in responses if r['status']==200)
            journal=MaterialHistory(ROOT/'data/material-history').read(operation)
            assert len(journal['transitions'])==1 and journal['applied'] is False
            report['after_concurrent']=journal
        else:
            undo=request('/materials/history',payload)
        assert digest()==applied[0]['texture'];capture('undo')
        try:
            request('/materials/history',dict(operation_id=operation,direction='redo',revision=operation,confirmed=True))
            raise AssertionError('Stale revision accepted')
        except HTTPError as error:
            assert error.code==400;report['stale_rejection']=json.load(error)
        redo=request('/materials/history',dict(operation_id=operation,direction='redo',revision=undo['revision'],confirmed=True))
        assert digest()==applied[1]['texture'];capture('redo')
        if args.recovery:
            from carla_safety_agent.material_history import MaterialHistory
            history=MaterialHistory(ROOT/'data/material-history')
            confirmed=history.read(operation)
            request('/materials/restore',selection)
            assert digest() is None
            before=set(history.root.glob('*.json'))
            def injected():
                raise RuntimeError('Controlled fixture: uncertain journal after separately acknowledged native application')
            # Recreate B independently: the concurrent branch reuses payload for HTTP JSON.
            buffer=io.BytesIO();Image.new('RGB',(1024,1024),(220,0,220)).save(buffer,format='PNG')
            payload_bytes=buffer.getvalue()
            result=request('/materials/apply?'+urllib.parse.urlencode(selection),payload_bytes)
            assert result['texture']==applied[1]['texture']
            try:
                history.execute(confirmed['identity'],None,applied[1]['texture'],injected)
                raise AssertionError('Injected failure did not propagate')
            except RuntimeError as error:
                assert 'requires inspection' in str(error)
            failures=[history.read(p.stem) for p in set(history.root.glob('*.json'))-before]
            failed=next(row for row in failures if row['state']=='needs_attention')
            report['injection_scope']='Synthetic uncertain journal after separate real HTTP application; not an interrupted native transaction or crash'
            report['injected_failure']=failed
            assert digest()==applied[1]['texture'];capture('injected-failure')
            failed_bytes=history.path(failed['operation_id']).read_bytes()
            try:
                request('/materials/restore',selection)
                raise AssertionError('New edit accepted while slot unresolved')
            except HTTPError as error:
                assert error.code==400
                report['unresolved_edit_rejection']=json.load(error)
            assert digest()==applied[1]['texture']
            assert history.path(failed['operation_id']).read_bytes()==failed_bytes
            try:
                request('/materials/history',dict(operation_id=result['material_operation_id'],
                    revision=result['material_operation_id'],direction='undo',confirmed=True))
            except HTTPError as error:
                assert error.code==400
                report['unresolved_old_undo_rejection']=json.load(error)
            else:raise AssertionError('Old undo bypassed unresolved environment slot')
            assert digest()==applied[1]['texture']
            inspected=request('/materials/history-inspection?operation_id='+failed['operation_id'])
            assert inspected['registry_matches']=='target'
            recovery_request=dict(operation_id=failed['operation_id'],inspection_token=inspected['inspection_token'],
                choice='source',registered_texture=inspected['registered_texture'],confirmed=True)
            recovered=request('/materials/history-recover',recovery_request)
            assert recovered['recovery']['state']=='confirmed' and digest() is None
            final=history.read(failed['operation_id'])
            assert final['state']==failed['state'] and final['error']==failed['error']
            capture('explicit-recovery')
            try:
                request('/materials/history-recover',recovery_request)
                raise AssertionError('Repeated recovery accepted')
            except HTTPError as error:
                assert error.code==400
                report['recovery_repeat_rejection']=json.load(error)
            report['recovery']=recovered
        report.update(passed=True,selection=selection,applied=applied,undo=undo,redo=redo)
    finally:
        try:
            if attempted:
                if digest() is not None:
                    report['cleanup']=request('/materials/restore',selection)
                else:
                    report['cleanup']={'already_without_registered_override':True}
                assert digest() is None;capture('restored')
        except Exception as error:
            report.update(passed=False,cleanup_error=str(error))
        try:
            assert client.get_world().id==world.id
            spectator.set_transform(camera)
        except Exception as error:report.update(passed=False,camera_error=str(error))
        (output/'report.json').write_text(json.dumps(report,indent=2))
        print(json.dumps({'output':str(output),'passed':report['passed']}))
    if not report['passed']:raise RuntimeError('Material history validation failed')


if __name__=='__main__':main()

"""Real one-frame excerpt publication and controlled lock rejection; preserve all evidence."""
import argparse
from contextlib import nullcontext
import json
import time
import uuid
from urllib.error import HTTPError
from carla_safety_agent.capture_quota import capture_write_lock
from carla_safety_agent.capture_recovery import inventory
from carla_safety_agent.scene_store import identifier
from cleanup_superseded_model_captures import idle
from regression_material_slots import ROOT,request


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('run_id');args=parser.parse_args()
    identifier(args.run_id);idle()
    datasets=ROOT/'.runtime/generated-scenarios';source=datasets/args.run_id
    before,size=inventory(source)
    assert size<100*1024**2,'Use a small reviewed test recording'
    frame=json.loads((source/'index.json').read_text())['frames'][0]['frame']
    output=ROOT/'runs/validation'/('excerpt-admission-'+uuid.uuid4().hex+'.json')
    report={'passed':False,'source':args.run_id,'cases':[]}
    try:
        for conflict in (False,True):
            request_id=uuid.uuid4().hex
            row={'request_id':request_id,'conflict':conflict};report['cases'].append(row)
            with capture_write_lock(datasets) if conflict else nullcontext():
                row['started']=request('/datasets/excerpt',dict(run_id=args.run_id,request_id=request_id,frame=frame,before_s=0,after_s=0,confirmed=True))
                deadline=time.monotonic()+90
                while time.monotonic()<deadline:
                    status=request('/datasets/excerpt?request_id='+request_id)
                    row['status']=status
                    if status['state']!='running':break
                    time.sleep(.5)
                else:raise TimeoutError('Excerpt job still running; inspect this request ID before retrying')
            if conflict:
                assert status['state']=='failed' and 'admission lock' in status['error']
                assert 'excerpt_run_id' not in status
                staging=ROOT/'.runtime/dataset-excerpts'/request_id
                copies=list(staging.glob('excerpt-*/manifest.json'));assert len(copies)==1
                assert not (datasets/copies[0].parent.name).exists()
                row['retained_staging']=str(copies[0].parent)
                try:
                    request('/datasets/excerpt/download?request_id='+request_id,raw=True)
                    raise AssertionError('Failed excerpt download accepted')
                except HTTPError as error:assert error.code==400
            else:
                assert status['state']=='ready' and status['raw_data_verified'] is True
                published=datasets/status['excerpt_run_id']
                assert json.loads((published/'manifest.json').read_text())['frame_count']==1
                assert request('/datasets/excerpt/download?request_id='+request_id,raw=True)[:2]==b'PK'
            assert inventory(source)[0]==before,'Source changed'
        idle();report['passed']=True
    except Exception as error:
        report['error']=str(error);raise
    finally:
        output.write_text(json.dumps(report,indent=2));print(json.dumps({'receipt':str(output),'passed':report['passed']}),flush=True)


if __name__=='__main__':main()

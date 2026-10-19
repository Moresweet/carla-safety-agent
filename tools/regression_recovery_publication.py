"""Recover one small inactive recording via the real service; never edit source."""
import argparse
import json
import time
import uuid
from carla_safety_agent.capture_recovery import inventory,require_inactive_execution
from carla_safety_agent.scene_store import identifier
from cleanup_superseded_model_captures import idle
from regression_material_slots import ROOT,request


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('run_id');args=parser.parse_args()
    identifier(args.run_id);idle()
    source=ROOT/'.runtime/generated-scenarios'/args.run_id
    before,size=inventory(source);assert size<100*1024**2,'Use a small reviewed fixture'
    manifest=json.loads((source/'manifest.json').read_text())
    require_inactive_execution(ROOT/'data',manifest['execution_id'])
    request_id=uuid.uuid4().hex
    output=ROOT/'runs/validation'/('recovery-publication-'+request_id+'.json')
    report={'passed':False,'request_id':request_id,'source':args.run_id}
    payload=dict(run_id=args.run_id,request_id=request_id,confirmed=True)
    try:
        report['started']=request('/datasets/recovery',payload)
        deadline=time.monotonic()+90
        while time.monotonic()<deadline:
            result=request('/datasets/recovery?request_id='+request_id);report['result']=result
            if result['state']!='running':break
            time.sleep(.5)
        else:raise TimeoutError('Recovery still running; inspect the existing request before retrying')
        assert result['state']=='recovered',result
        recovered=ROOT/'.runtime/generated-scenarios'/result['recovered_run_id']
        restored=json.loads((recovered/'manifest.json').read_text())
        assert restored['status']=='saved_recovered' and restored['frame_count']>0
        assert inventory(source)[0]==before,'Source changed'
        duplicate=request('/datasets/recovery',payload)
        assert duplicate['recovered_run_id']==result['recovered_run_id']
        report.update(passed=True,frame_count=restored['frame_count'],source_unchanged=True,same_request_reused=True)
        idle()
    except Exception as error:report.update(passed=False,error=str(error));raise
    finally:
        output.write_text(json.dumps(report,indent=2));print(json.dumps({'receipt':str(output),'passed':report['passed']}),flush=True)


if __name__=='__main__':main()

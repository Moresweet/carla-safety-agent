"""Real HTTP rejection of an existing zero-sample capture; no new recording."""
import json
import time
import uuid
from cleanup_superseded_model_captures import idle
from regression_scene_versions import ROOT, request
from carla_safety_agent.capture_recovery import inventory


def main():
    source_id='capture-20260929T141403-17dd8aed'
    source=ROOT/'.runtime/generated-scenarios'/source_id
    idle()
    before=inventory(source)
    manifest=json.loads((source/'manifest.json').read_text())
    assert manifest['run_id']==source_id and manifest['frame_count']==0
    request_id=uuid.uuid4().hex
    payload={'run_id':source_id,'request_id':request_id,'confirmed':True}
    report={'passed':False,'request_id':request_id,'source':source_id}
    output=ROOT/'runs/validation'/('empty-recovery-'+request_id+'.json')
    try:
        request('datasets/recovery',payload)
        deadline=time.monotonic()+30
        while True:
            result=request('datasets/recovery?request_id='+request_id)
            if result['state']!='running':break
            if time.monotonic()>deadline:raise TimeoutError('Inspect original request; do not retry')
            time.sleep(.2)
        report['result']=result
        assert result['state']=='failed' and '没有已提交样本可恢复' in result['error']
        assert 'recovered_run_id' not in result and 'candidate_run_id' not in result
        staging=ROOT/'.runtime/dataset-recovery/copies'/request_id
        assert staging.is_dir() and not list(staging.iterdir())
        assert request('datasets/recovery',payload)['state']=='failed'
        assert inventory(source)==before
        idle()
        assert request('system/preflight')['ready']
        report.update(passed=True,source_unchanged=True,same_request_did_not_restart=True)
    finally:
        output.write_text(json.dumps(report,indent=2,ensure_ascii=False))
        print(json.dumps({'receipt':str(output),'passed':report['passed']}))


if __name__=='__main__':main()

"""Exercise real disk measurement with a process-local low quota; retain staged data."""
import argparse
import json
import os
from pathlib import Path
import uuid
from carla_safety_agent.capture_quota import publish_capture,capture_quota_policy
from carla_safety_agent.capture_storage import inventory_captures
from carla_safety_agent.capture_recovery import inventory
from cleanup_superseded_model_captures import idle
from regression_material_slots import ROOT


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('excerpt_receipt',type=Path)
    args=parser.parse_args();idle()
    receipt=json.loads(args.excerpt_receipt.read_text())
    assert receipt['passed'] is True
    case=next(row for row in receipt['cases'] if row['conflict'])
    staged=Path(case['retained_staging'])
    assert staged.parent==ROOT/'.runtime/dataset-excerpts'/case['request_id']
    assert not staged.parent.is_symlink() and not staged.is_symlink()
    datasets=ROOT/'.runtime/generated-scenarios'
    before,size=inventory(staged);assert size<100*1024**2
    usage=inventory_captures(datasets)
    assert usage['complete'] and usage['allocated_bytes']>1024**3
    target=datasets/staged.name;assert not target.exists() and not target.is_symlink()
    previous=os.environ.get('CSA_CAPTURE_QUOTA_GIB')
    report={'passed':False,'staged':str(staged),'allocated_before':usage['allocated_bytes'],
            'scope':'Real production publish function and disk measurement; process-local 1 GiB limit, not HTTP service quota configuration'}
    output=ROOT/'runs/validation'/('publish-quota-rejection-'+uuid.uuid4().hex+'.json')
    try:
        os.environ['CSA_CAPTURE_QUOTA_GIB']='1'
        report['test_policy']=capture_quota_policy()
        try:publish_capture(staged,datasets)
        except ValueError as error:
            report['rejection']=str(error)
            assert 'quota reached' in str(error) and 'staged copy retained' in str(error)
        else:raise AssertionError('Quota rejection expected')
        assert inventory(staged)[0]==before and not target.exists()
        report.update(passed=True,staged_files_unchanged=True,destination_absent=True)
    finally:
        if previous is None:os.environ.pop('CSA_CAPTURE_QUOTA_GIB',None)
        else:os.environ['CSA_CAPTURE_QUOTA_GIB']=previous
        report['restored_process_policy']=capture_quota_policy()
        output.write_text(json.dumps(report,indent=2))
        print(json.dumps({'receipt':str(output),'passed':report['passed']}),flush=True)


if __name__=='__main__':main()

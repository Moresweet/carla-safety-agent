import json
import pytest
from carla_safety_agent.dataset_execution import execution_summary


@pytest.mark.parametrize('fault',[None,'missing','identity','state','link'])
def test_execution_summary_does_not_infer_success(tmp_path,fault):
    folder=tmp_path/'execution-one'; folder.mkdir()
    record={'run_id':'execution-one','state':'failed','error':'simulator stopped'}
    if fault=='identity':record['run_id']='other'
    if fault=='state':record['state']='passed'
    path=folder/'execution.json'
    if fault=='link':path.symlink_to('/nonexistent')
    elif fault!='missing':path.write_text(json.dumps(record))
    result=execution_summary(tmp_path,'execution-one')
    assert result['available']==(fault is None)
    if fault is None:assert result['state']=='failed' and result['error']=='simulator stopped'


def test_bad_identity_is_unavailable(tmp_path):
    for key in (None,'../outside','/etc/passwd'):
        assert not execution_summary(tmp_path,key)['available']


def test_listing_keeps_capture_status_separate_and_source_unchanged(tmp_path):
    from carla_safety_agent.dataset import list_datasets
    run=tmp_path/'captures/capture-one'; run.mkdir(parents=True)
    manifest=run/'manifest.json'
    manifest.write_text('{"run_id":"capture-one","status":"saved","execution_id":"execution-one"}')
    original=manifest.read_bytes()
    experiment=tmp_path/'experiments/execution-one'; experiment.mkdir(parents=True)
    (experiment/'execution.json').write_text('{"run_id":"execution-one","state":"failed","error":"server died"}')
    result=list_datasets(tmp_path/'captures',experiments_root=tmp_path/'experiments')
    assert result[0]['status']=='saved'
    assert result[0]['execution_summary']['state']=='failed'
    assert manifest.read_bytes()==original
    assert 'execution_summary' not in list_datasets(tmp_path/'captures')[0]

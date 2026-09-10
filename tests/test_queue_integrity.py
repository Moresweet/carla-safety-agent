import copy
import json
import pytest
from carla_safety_agent.experiment_queue import ExperimentQueue
from carla_safety_agent.batch_catalog import BatchCatalog


def queue(tmp_path):
    q=ExperimentQueue(tmp_path/'queue')
    q.create({**{a:[{'id':'base','configuration':{}}] for a in ('scenes','models','weather','textures')},'seeds':[1,2]})
    claim=q.claim();q.update_attempt(claim['job_id'],claim['attempt']['attempt_id'],execution_id='run1')
    return q


@pytest.mark.parametrize('defect',['schema','pause','order','pending_live','multiple_active','duplicate_attempt',
    'duplicate_execution','historical_live','created_bool','missing_execution','ended','attempt_count','result_type','execution_type'])
def test_corrupt_ownership_is_not_repaired_or_overwritten(tmp_path,defect):
    q=queue(tmp_path);state=q.read();first,second=state['jobs'];attempt=first['attempts'][0]
    if defect=='schema':state['schema_version']='other'
    if defect=='pause':state['paused']='false'
    if defect=='order':state['jobs'].reverse()
    if defect=='pending_live':first['state']='pending'
    if defect in ('multiple_active','duplicate_attempt','duplicate_execution'):
        second.update(state='running',attempts=[copy.deepcopy(attempt)])
        if defect!='duplicate_attempt':second['attempts'][0]['attempt_id']='attempt2'
        if defect!='duplicate_execution':second['attempts'][0]['execution_id']='run2'
    if defect=='historical_live':first['attempts'].append({**attempt,'attempt_id':'attempt2','execution_id':'run2'})
    if defect=='created_bool':attempt['created_at']=True
    if defect=='missing_execution':attempt['execution_id']=None
    if defect=='result_type':attempt['result']='invalid'
    if defect=='execution_type':attempt['result']={'execution':'invalid'}
    if defect=='ended':
        first['state']=attempt['state']='failed';attempt.update(ended_at=-1,result={})
    if defect=='attempt_count':first['attempts']*=21
    path=q.root/'queue.json';before=path.read_bytes()
    with pytest.raises(ValueError):q.write(state)
    assert path.read_bytes()==before
    path.write_text(json.dumps(state));damaged=path.read_bytes()
    for operation in (q.read,q.claim,lambda:q.set_paused(True)):
        with pytest.raises(ValueError):operation()
        assert path.read_bytes()==damaged


@pytest.mark.parametrize('raw',['{"schema_version":"carla-experiment-queue/1","schema_version":"other"}','{"paused":NaN}'])
def test_queue_duplicate_keys_and_nonfinite_json_rejected(tmp_path,raw):
    q=queue(tmp_path);path=q.root/'queue.json';path.write_text(raw)
    with pytest.raises(ValueError):q.read()
    assert path.read_text()==raw


def test_queue_file_link_is_not_followed_by_direct_dispatcher(tmp_path):
    q=queue(tmp_path);path=q.root/'queue.json';outside=tmp_path/'other.json'
    path.rename(outside);path.symlink_to(outside);before=outside.read_bytes()
    with pytest.raises(ValueError):q.claim()
    assert outside.read_bytes()==before


def test_catalog_surfaces_invalid_ledger_as_error(tmp_path):
    q=queue(tmp_path);state=q.read();state['jobs'][0]['state']='pending'
    (q.root/'queue.json').write_text(json.dumps(state))
    assert BatchCatalog(tmp_path).list()['batches'][0]['error']


def test_queue_directory_and_lock_links_rejected(tmp_path):
    q=queue(tmp_path);linked=tmp_path/'alias';linked.symlink_to(q.root,target_is_directory=True)
    with pytest.raises(ValueError):ExperimentQueue(linked)
    lock=q.root/'queue.lock';original=tmp_path/'original.lock';lock.rename(original);lock.symlink_to(original)
    before=(q.root/'queue.json').read_bytes()
    with pytest.raises(ValueError):q.set_paused(True)
    assert (q.root/'queue.json').read_bytes()==before

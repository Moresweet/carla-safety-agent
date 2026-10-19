import json
from unittest.mock import patch
import pytest
from carla_safety_agent.recovery_service import RecoveryService


@pytest.mark.parametrize('after_rename',[False,True])
def test_actual_process_exit_preserves_publish_intent(tmp_path,monkeypatch,after_rename):
    import os
    import subprocess
    import sys
    from pathlib import Path
    service,source,data=fixture(tmp_path,monkeypatch)
    before=(source/'manifest.json').read_bytes()
    with patch('threading.Thread.start'):service.start(data)
    code='''
import json, os, sys
from pathlib import Path
import carla_safety_agent.recovery_service as module
root=Path(sys.argv[1])
service=module.RecoveryService(root/'datasets',root/'reports',root/'data','unused','unused')
request_id='a'*32
row=json.loads(service._path(request_id).read_text())
# Isolate raw-copy validation from this process-exit/journal test.
def recover(source,staging,*args):
    output=staging/('recovered-'+'b'*32);output.mkdir()
    (output/'manifest.json').write_text(json.dumps({'run_id':output.name}))
    (output/'raw.bin').write_bytes(b'preserved fixture')
    return output
module.recover_capture=recover
module.require_inactive_execution=lambda *_:None
real_publish=module.publish_capture
def publish(output,destination):
    if sys.argv[2]=='after':real_publish(output,destination)
    os._exit(23)
module.publish_capture=publish
service._run(row,root/'datasets/capture-original','execution')
'''
    result=subprocess.run([sys.executable,'-c',code,str(tmp_path),'after' if after_rename else 'before'],
        env=dict(os.environ,PYTHONPATH=str(Path(__file__).resolve().parents[1]/'src'),CSA_CAPTURE_QUOTA_GIB='100'),
        capture_output=True,text=True,timeout=15)
    assert result.returncode==23,result.stderr
    durable=service._path(data['request_id']).read_bytes()
    restarted=RecoveryService(service.datasets,service.reports,service.data_root,'unused','unused')
    with patch('threading.Thread.start') as thread:
        status=restarted.start(data);thread.assert_not_called()
    assert status['state']=='needs_attention' and status['phase']=='publishing'
    assert status['candidate_presence']['staged']==(not after_rename)
    assert status['candidate_presence']['published']==after_rename
    assert status['candidate_presence']['raw_data_verified'] is False
    assert 'recovered_run_id' not in status
    candidate=status['candidate_run_id']
    staged=Path(status['staging_directory'])/candidate
    published=service.datasets/candidate
    assert staged.exists()!=after_rename and published.exists()==after_rename
    assert ((published if after_rename else staged)/'raw.bin').read_bytes()==b'preserved fixture'
    assert service._path(data['request_id']).read_bytes()==durable
    assert (source/'manifest.json').read_bytes()==before


def fixture(tmp_path,monkeypatch):
    source=tmp_path/'datasets/capture-original';source.mkdir(parents=True)
    (source/'manifest.json').write_text(json.dumps({'run_id':'capture-original','status':'recording','execution_id':'execution'}))
    service=RecoveryService(source.parent,tmp_path/'reports',tmp_path/'data','validator','python')
    monkeypatch.setattr('carla_safety_agent.recovery_service.require_inactive_execution',lambda *_:None)
    data={'run_id':source.name,'request_id':'a'*32,'confirmed':True}
    return service,source,data


@pytest.mark.parametrize('status',['recording','saved_cleanup_error','saved_capture_error'])
def test_explicit_confirmation_idempotency_and_restart(tmp_path,monkeypatch,status):
    service,source,data=fixture(tmp_path,monkeypatch)
    manifest=json.loads((source/'manifest.json').read_text());manifest['status']=status
    (source/'manifest.json').write_text(json.dumps(manifest))
    for invalid in ({**data,'confirmed':1},{**data,'request_id':'../escape'},{**data,'extra':1}):
        with pytest.raises(ValueError):service.start(invalid)
    with patch('threading.Thread.start') as start:
        first=service.start(data)
        assert service.start(data)==first and start.call_count==1
        with pytest.raises(ValueError,match='another source'):service.start({**data,'run_id':'capture-other'})
        with pytest.raises(ValueError,match='running'):service.start({**data,'request_id':'b'*32})
    restarted=RecoveryService(service.datasets,service.reports,service.data_root,'validator','python')
    assert restarted.status(data['request_id'])['state']=='needs_attention'


@pytest.mark.parametrize('status',['saved','saved_limit','saved_recovered','unknown'])
def test_noninterrupted_status_never_launches_recovery(tmp_path,monkeypatch,status):
    service,source,data=fixture(tmp_path,monkeypatch)
    manifest=json.loads((source/'manifest.json').read_text());manifest['status']=status
    (source/'manifest.json').write_text(json.dumps(manifest))
    with patch('threading.Thread.start') as start:
        with pytest.raises(ValueError,match='not interrupted'):service.start(data)
        start.assert_not_called()
    assert not service.reports.exists()


@pytest.mark.parametrize('failure',[None,'changed','audit','publish','quota','busy'])
def test_background_copy_publishes_only_verified_output(tmp_path,monkeypatch,failure):
    service,source,data=fixture(tmp_path,monkeypatch)
    with patch('threading.Thread.start'):row=service.start(data)
    def recover(*args):
        if failure=='audit':raise ValueError('raw scan failed')
        result=args[1]/('recovered-'+'b'*32);result.mkdir();(result/'manifest.json').write_text('{}')
        if failure=='publish':(service.datasets/result.name).mkdir()
        return result
    monkeypatch.setattr('carla_safety_agent.recovery_service.recover_capture',recover)
    if failure=='changed':(source/'manifest.json').write_text('{}')
    from contextlib import nullcontext
    from carla_safety_agent.capture_quota import capture_write_lock
    if failure=='quota':monkeypatch.setattr('carla_safety_agent.capture_quota.check_capture_quota',lambda *_:('capture_quota','quota reached'))
    with capture_write_lock(service.datasets) if failure=='busy' else nullcontext():
        service._run(row,source,'execution')
    result=service.status(data['request_id'])
    assert service.active is None
    assert result['state']==('failed' if failure else 'recovered')
    assert (source/'manifest.json').exists()
    if failure in ('publish','quota','busy'):assert (service.reports/'copies'/data['request_id']/('recovered-'+'b'*32)/'manifest.json').exists()
    if failure in ('quota','busy'):
        assert not (service.datasets/('recovered-'+'b'*32)).exists()
        assert json.loads((source/'manifest.json').read_text())['run_id']=='capture-original'
        assert result.get('recovered_run_id') is None
    if failure is None:assert (service.datasets/('recovered-'+'b'*32)/'manifest.json').exists()


def test_publication_intent_survives_service_loss_without_false_success(tmp_path,monkeypatch):
    service,source,data=fixture(tmp_path,monkeypatch)
    with patch('threading.Thread.start'):row=service.start(data)
    def recover(*args):
        result=args[1]/('recovered-'+'b'*32);result.mkdir();(result/'manifest.json').write_text('{}');return result
    monkeypatch.setattr('carla_safety_agent.recovery_service.recover_capture',recover)
    observed=[]
    def publish(output,destination):
        durable=json.loads(service._path(data['request_id']).read_text())
        assert durable['phase']=='publishing' and durable['candidate_run_id']==output.name
        restarted=RecoveryService(service.datasets,service.reports,service.data_root,'validator','python')
        with patch('threading.Thread.start') as thread:
            status=restarted.start(data);thread.assert_not_called()
        assert status['state']=='needs_attention' and 'recovered_run_id' not in status
        assert status['staging_directory']==str(output.parent)
        observed.append(status)
        raise OSError('Injected publication interruption')
    monkeypatch.setattr('carla_safety_agent.recovery_service.publish_capture',publish)
    service._run(row,source,'execution')
    assert len(observed)==1
    assert service.status(data['request_id'])['state']=='failed'

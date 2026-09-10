import fcntl
import json
from unittest.mock import patch
import pytest
from carla_safety_agent.bundle_registration_service import BundleRegistrationService,native_import_busy
from carla_safety_agent.bundle_workbench import BundleWorkbench
from test_bundle_registration import setup


def fixture(tmp_path):
    archive,project,_=setup(tmp_path)
    workbench=BundleWorkbench(project);workbench.root.mkdir(parents=True)
    source=workbench.path('source');source.write_bytes(archive.read_bytes())
    service=BundleRegistrationService(workbench,lambda:None)
    data={'bundle_id':'source','request_id':'a'*32,'confirmed':True}
    return service,source,data


def test_native_lock_probe_observes_real_exclusion(tmp_path):
    assert not native_import_busy(tmp_path)
    path=tmp_path/'.runtime/blender-assets/import.lock';path.parent.mkdir(parents=True)
    with path.open('a') as stream:
        fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        assert native_import_busy(tmp_path)
    assert not native_import_busy(tmp_path)


def test_registration_is_explicit_idempotent_and_restart_does_not_retry(tmp_path):
    service,source,data=fixture(tmp_path)
    for invalid in ({**data,'confirmed':1},{**data,'request_id':'../bad'},{**data,'extra':True}):
        with pytest.raises(ValueError):service.start(invalid)
    with patch('threading.Thread.start') as start:
        row=service.start(data);assert service.start(data)==row and start.call_count==1
        with pytest.raises(ValueError,match='another package'):service.start({**data,'bundle_id':'other'})
        with pytest.raises(ValueError,match='running'):service.start({**data,'request_id':'b'*32})
    assert BundleRegistrationService(service.workbench,lambda:None).status(data['request_id'])['state']=='needs_attention'


@pytest.mark.parametrize('failure',[None,'changed','native','busy'])
def test_registration_worker_retains_source_and_reports_failure(tmp_path,monkeypatch,failure):
    service,source,data=fixture(tmp_path);before=source.read_bytes()
    with patch('threading.Thread.start'):row=service.start(data)
    calls=[]
    def register(path,project,output,**kwargs):
        calls.append(True);assert kwargs['execute'] is True
        if failure=='native':raise RuntimeError('native exit nonzero')
        output.write_bytes(before);return {'state':'registered','restored':False}
    monkeypatch.setattr('carla_safety_agent.bundle_registration_service.register_bundle',register)
    if failure=='changed':source.write_bytes(b'changed')
    if failure=='busy':service.require_idle=lambda:(_ for _ in ()).throw(ValueError('active model'))
    service._run(row,source)
    result=service.status(data['request_id'])
    assert result['state']==('needs_attention' if failure else 'registered')
    assert service.active is None
    if failure in ('changed','busy'):assert not calls
    if failure!='changed':assert source.read_bytes()==before


def test_active_model_rejected_before_registration_report(tmp_path):
    service,source,data=fixture(tmp_path)
    service.require_idle=lambda:(_ for _ in ()).throw(ValueError('active model'))
    with pytest.raises(ValueError,match='active'):service.start(data)
    assert not service.root.exists()

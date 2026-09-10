import json
from unittest.mock import patch
import pytest
from carla_safety_agent.recovery_service import RecoveryService


def fixture(tmp_path,monkeypatch):
    source=tmp_path/'datasets/capture-original';source.mkdir(parents=True)
    (source/'manifest.json').write_text(json.dumps({'run_id':'capture-original','status':'recording','execution_id':'execution'}))
    service=RecoveryService(source.parent,tmp_path/'reports',tmp_path/'data','validator','python')
    monkeypatch.setattr('carla_safety_agent.recovery_service.require_inactive_execution',lambda *_:None)
    data={'run_id':source.name,'request_id':'a'*32,'confirmed':True}
    return service,source,data


def test_explicit_confirmation_idempotency_and_restart(tmp_path,monkeypatch):
    service,source,data=fixture(tmp_path,monkeypatch)
    for invalid in ({**data,'confirmed':1},{**data,'request_id':'../escape'},{**data,'extra':1}):
        with pytest.raises(ValueError):service.start(invalid)
    with patch('threading.Thread.start') as start:
        first=service.start(data)
        assert service.start(data)==first and start.call_count==1
        with pytest.raises(ValueError,match='another source'):service.start({**data,'run_id':'capture-other'})
        with pytest.raises(ValueError,match='running'):service.start({**data,'request_id':'b'*32})
    restarted=RecoveryService(service.datasets,service.reports,service.data_root,'validator','python')
    assert restarted.status(data['request_id'])['state']=='needs_attention'


@pytest.mark.parametrize('failure',[None,'changed','audit','publish'])
def test_background_copy_publishes_only_verified_output(tmp_path,monkeypatch,failure):
    service,source,data=fixture(tmp_path,monkeypatch)
    with patch('threading.Thread.start'):row=service.start(data)
    def recover(*args):
        if failure=='audit':raise ValueError('raw scan failed')
        result=args[1]/'recovered-test';result.mkdir();(result/'manifest.json').write_text('{}')
        if failure=='publish':(service.datasets/result.name).mkdir()
        return result
    monkeypatch.setattr('carla_safety_agent.recovery_service.recover_capture',recover)
    if failure=='changed':(source/'manifest.json').write_text('{}')
    service._run(row,source,'execution')
    result=service.status(data['request_id'])
    assert service.active is None
    assert result['state']==('failed' if failure else 'recovered')
    assert (source/'manifest.json').exists()
    if failure=='publish':assert (service.reports/'copies/recovered-test/manifest.json').exists()
    if failure is None:assert (service.datasets/'recovered-test/manifest.json').exists()

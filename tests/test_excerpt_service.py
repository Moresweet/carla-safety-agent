from unittest.mock import patch
import pytest
from carla_safety_agent.excerpt_service import ExcerptService
from test_capture_excerpt import fixture


def setup(tmp_path,monkeypatch):
    source,_,_=fixture(tmp_path)
    service=ExcerptService(tmp_path,tmp_path/'reports',tmp_path/'data','validator','python')
    monkeypatch.setattr('carla_safety_agent.excerpt_service.require_inactive_execution',lambda *_:None)
    monkeypatch.setattr('carla_safety_agent.capture_excerpt.audit_capture',lambda *_:{'state':'passed'})
    data={'run_id':source.name,'request_id':'a'*32,'frame':12,'before_s':.1,'after_s':.1,'confirmed':True}
    return service,source,data


def test_explicit_request_idempotency_and_restart(tmp_path,monkeypatch):
    service,source,data=setup(tmp_path,monkeypatch)
    for invalid in ({**data,'confirmed':1},{**data,'request_id':'../escape'},{**data,'extra':1}):
        with pytest.raises(ValueError):service.start(invalid)
    with patch('threading.Thread.start') as start:
        row=service.start(data)
        assert service.start(data)==row and start.call_count==1
        with pytest.raises(ValueError,match='another selection'):service.start({**data,'frame':13})
        with pytest.raises(ValueError,match='Another excerpt'):service.start({**data,'request_id':'b'*32})
    restarted=ExcerptService(service.datasets,service.reports,service.data_root,'validator','python')
    assert restarted.status(data['request_id'])['state']=='needs_attention'
    with pytest.raises(ValueError,match='not ready'):restarted.download(data['request_id'])


@pytest.mark.parametrize('fault',[None,'changed','audit','active','quota','busy'])
def test_only_verified_copy_published_and_download_hash_checked(tmp_path,monkeypatch,fault):
    service,source,data=setup(tmp_path,monkeypatch)
    with patch('threading.Thread.start'):row=service.start(data)
    if fault=='changed':(source/'manifest.json').write_text('{}')
    if fault=='audit':monkeypatch.setattr('carla_safety_agent.capture_excerpt.audit_capture',lambda *_:{'state':'failed'})
    if fault=='active':
        def active(*_):raise ValueError('worker active')
        monkeypatch.setattr('carla_safety_agent.excerpt_service.require_inactive_execution',active)
    from contextlib import nullcontext
    from carla_safety_agent.capture_quota import capture_write_lock
    before=(source/'manifest.json').read_bytes()
    if fault=='quota':monkeypatch.setattr('carla_safety_agent.capture_quota.check_capture_quota',lambda *_:('capture_quota','quota reached'))
    with capture_write_lock(service.datasets) if fault=='busy' else nullcontext():
        service._run(row,source,'execution')
    result=service.status(data['request_id'])
    assert result['state']==('failed' if fault else 'ready') and service.active is None
    if fault:
        assert not list(tmp_path.glob('excerpt-*'))
        with pytest.raises(ValueError):service.download(data['request_id'])
        if fault in ('quota','busy'):
            assert (source/'manifest.json').read_bytes()==before
            assert list((service.reports/data['request_id']).glob('excerpt-*/manifest.json'))
            assert result.get('excerpt_run_id') is None
    else:
        assert (tmp_path/result['excerpt_run_id']/'manifest.json').is_file()
        archive=service.download(data['request_id']);archive.write_bytes(b'changed')
        with pytest.raises(ValueError,match='changed'):service.download(data['request_id'])


def test_thread_launch_failure_is_terminal(tmp_path,monkeypatch):
    service,_,data=setup(tmp_path,monkeypatch)
    with patch('threading.Thread.start',side_effect=RuntimeError('launch failed')):
        with pytest.raises(RuntimeError):service.start(data)
    assert service.active is None and service.status(data['request_id'])['state']=='failed'

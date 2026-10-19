import json
from unittest.mock import patch
import pytest
from carla_safety_agent.archive_service import ArchiveService


def fixture(tmp_path,monkeypatch):
    source=tmp_path/'datasets/capture-test';source.mkdir(parents=True)
    (source/'manifest.json').write_text(json.dumps({'run_id':source.name,'execution_id':'execution','status':'saved'}))
    monkeypatch.setattr('carla_safety_agent.archive_service.require_inactive_execution',lambda *_:None)
    return ArchiveService(source.parent,tmp_path/'reports',tmp_path/'data'),source,{'run_id':source.name,'request_id':'a'*32,'confirmed':True}


def test_confirmation_dedup_and_restart(tmp_path,monkeypatch):
    service,source,data=fixture(tmp_path,monkeypatch)
    with pytest.raises(ValueError):service.start({**data,'confirmed':1})
    with patch('threading.Thread.start') as launch:
        row=service.start(data)
        assert service.start(data)==row and launch.call_count==1
        with pytest.raises(ValueError):service.start({**data,'run_id':'other'})
        with pytest.raises(ValueError):service.start({**data,'request_id':'b'*32})
    restarted=ArchiveService(service.datasets,service.reports,service.data_root)
    assert restarted.status(data['request_id'])['state']=='needs_attention'


@pytest.mark.parametrize('changed',[False,True])
def test_real_archive_worker_terminal_state(tmp_path,monkeypatch,changed):
    service,source,data=fixture(tmp_path,monkeypatch)
    with patch('threading.Thread.start'):row=service.start(data)
    if changed:(source/'manifest.json').write_text('{}')
    service._run(row,source,'execution')
    assert service.active is None
    result=service.status(data['request_id'])
    assert result['state']==('failed' if changed else 'archived')
    assert not result['source_removed'] and source.exists()
    assert (service.reports/(data['request_id']+'.zip')).exists()!=changed
    if not changed:
        with service.open_download(data['request_id']) as stream:
            assert stream.read()==(service.reports/result['archive_file']).read_bytes()
        # Lost response retry after completion must return exactly the same task.
        with patch('threading.Thread.start') as launch:
            assert service.start(data)==result
            launch.assert_not_called()


@pytest.mark.parametrize('damage',['bytes','link','pending'])
def test_download_refuses_changed_or_incomplete_archive(tmp_path,monkeypatch,damage):
    service,source,data=fixture(tmp_path,monkeypatch)
    with patch('threading.Thread.start'):row=service.start(data)
    if damage=='pending':
        with pytest.raises(ValueError):service.open_download(data['request_id'])
        return
    service._run(row,source,'execution')
    path=service.reports/(data['request_id']+'.zip')
    if damage=='bytes':
        payload=path.read_bytes();path.write_bytes(b'X'+payload[1:])
    else:
        original=path.with_suffix('.original');path.rename(original);path.symlink_to(original)
    with pytest.raises((ValueError,OSError)):service.open_download(data['request_id'])

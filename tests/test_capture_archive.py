import json
import zipfile
import pytest
from carla_safety_agent.capture_archive import archive_capture, verify_capture_archive, restore_capture_archive
from pathlib import Path


def fixture(tmp_path):
    source=tmp_path/'capture-source';source.mkdir()
    (source/'manifest.json').write_text(json.dumps({'run_id':source.name,'status':'saved_capture_error'}))
    (source/'raw.bin').write_bytes(bytes(range(256))*20)
    return source,tmp_path/'backup.zip'


def test_disk_admission_never_allocates_archive_or_restore(tmp_path,monkeypatch):
    from types import SimpleNamespace
    source,output=fixture(tmp_path)
    archive_capture(source,output,lambda:None)
    before={p.name:p.read_bytes() for p in source.iterdir()}
    monkeypatch.setattr('carla_safety_agent.capture_archive.shutil.disk_usage',lambda _:SimpleNamespace(free=1024**3))
    second=tmp_path/'second.zip'
    with pytest.raises(ValueError,match='available space'):archive_capture(source,second,lambda:None)
    assert not second.exists() and not second.with_name('second.zip.partial').exists()
    with pytest.raises(ValueError,match='free'):restore_capture_archive(output,tmp_path)
    assert not list(tmp_path.glob('capture-restore-*'))
    assert {p.name:p.read_bytes() for p in source.iterdir()}==before


def test_publication_race_does_not_overwrite_other_output(tmp_path):
    source,output=fixture(tmp_path);calls=[]
    def inactive():
        calls.append(1)
        if len(calls)==2:output.write_bytes(b'created by another caller')
    with pytest.raises(FileExistsError):archive_capture(source,output,inactive)
    assert output.read_bytes()==b'created by another caller'
    assert verify_capture_archive(output.with_name(output.name+'.partial'))['source_run_id']==source.name


@pytest.mark.parametrize('operation', ['archive', 'restore'])
def test_space_consumed_after_initial_admission_retains_only_partial(tmp_path, monkeypatch, operation):
    from types import SimpleNamespace
    source, output = fixture(tmp_path)
    if operation == 'restore':
        archive_capture(source, output, lambda: None)
    original = {p.name: p.read_bytes() for p in source.iterdir()}
    calls = []
    def disk(_):
        calls.append(1)
        return SimpleNamespace(free=10*1024**3 if len(calls) == 1 else 1024**3)
    monkeypatch.setattr('carla_safety_agent.capture_archive.shutil.disk_usage', disk)
    with pytest.raises(ValueError, match='disk reserve reached'):
        if operation == 'archive':
            archive_capture(source, output, lambda: None)
        else:
            restore_capture_archive(output, tmp_path)
    assert len(calls) == 2
    assert {p.name: p.read_bytes() for p in source.iterdir()} == original
    if operation == 'archive':
        assert not output.exists()
        assert output.with_name(output.name+'.partial').exists()
    else:
        stages = list(tmp_path.glob('capture-restore-*'))
        assert len(stages) == 1
        assert not (stages[0]/'restore-receipt.json').exists()
        assert verify_capture_archive(output)['source_run_id'] == source.name


def test_archive_write_failure_keeps_source_and_partial(tmp_path,monkeypatch):
    import errno
    source,output=fixture(tmp_path)
    before={p.name:p.read_bytes() for p in source.iterdir()}
    def fail(*args,**kwargs):raise OSError(errno.ENOSPC,'injected archive write failure')
    monkeypatch.setattr(zipfile.ZipFile,'write',fail)
    with pytest.raises(OSError):archive_capture(source,output,lambda:None)
    assert not output.exists() and output.with_name(output.name+'.partial').exists()
    assert {p.name:p.read_bytes() for p in source.iterdir()}==before


def test_archive_preserves_all_bytes_and_original(tmp_path):
    source,output=fixture(tmp_path);calls=[]
    before={p.name:p.read_bytes() for p in source.iterdir()}
    result=archive_capture(source,output,lambda:calls.append(1))
    assert result['verified'] and not result['source_removed'] and len(calls)==2
    assert verify_capture_archive(output)['source_run_id']==source.name
    with zipfile.ZipFile(output) as archive:
        for name,data in before.items():assert archive.read(name)==data
    assert {p.name:p.read_bytes() for p in source.iterdir()}==before
    with pytest.raises(ValueError):archive_capture(source,output,lambda:None)
    result=restore_capture_archive(output,tmp_path)
    restored=Path(result['directory'])
    assert restored!=source and not result['registered_for_replay']
    assert {p.name:p.read_bytes() for p in restored.iterdir()}==before
    assert json.loads((restored/'manifest.json').read_text())['status']=='saved_capture_error'
    assert restore_capture_archive(output,tmp_path)['directory']!=str(restored)


def test_changed_source_leaves_only_partial(tmp_path):
    source,output=fixture(tmp_path);calls=[]
    def inactive():
        calls.append(1)
        if len(calls)==2:(source/'raw.bin').write_bytes(b'changed externally')
    with pytest.raises(ValueError,match='changed'):archive_capture(source,output,inactive)
    assert not output.exists() and output.with_name(output.name+'.partial').exists()


def test_active_or_linked_source_rejected(tmp_path):
    source,output=fixture(tmp_path)
    def active():raise ValueError('active')
    with pytest.raises(ValueError,match='active'):archive_capture(source,output,active)
    (source/'linked').symlink_to(source/'raw.bin')
    with pytest.raises(ValueError,match='symbolic'):archive_capture(source,output,lambda:None)
    assert not output.exists()


@pytest.mark.parametrize('damage',['path','hash','identity','extra'])
def test_standalone_archive_rejects_invalid_content(tmp_path,damage):
    source,output=fixture(tmp_path)
    archive_capture(source,output,lambda:None)
    with zipfile.ZipFile(output) as archive:files={name:archive.read(name) for name in archive.namelist()}
    if damage=='path':files['../escape']=b'bad'
    if damage=='extra':files['extra']=b'bad'
    if damage=='hash':files['raw.bin']=b'changed'
    if damage=='identity':
        receipt=json.loads(files['capture-archive.json']);receipt['source_run_id']='another'
        files['capture-archive.json']=json.dumps(receipt).encode()
    broken=tmp_path/'broken.zip'
    with zipfile.ZipFile(broken,'w') as archive:
        for name,data in files.items():archive.writestr(name,data)
    with pytest.raises(ValueError):verify_capture_archive(broken)
    before=set(tmp_path.iterdir())
    with pytest.raises(ValueError):restore_capture_archive(broken,tmp_path)
    assert set(tmp_path.iterdir())==before

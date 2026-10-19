import pytest
from carla_safety_agent.capture_quota import check_capture_quota


def test_publish_counts_hardlinks_independently_of_unpublished_siblings(tmp_path,monkeypatch):
    import os
    from carla_safety_agent.capture_quota import publish_capture
    sibling=tmp_path/'staging/recovered-a';sibling.mkdir(parents=True)
    staged=sibling.parent/'recovered-z';staged.mkdir()
    (sibling/'manifest.json').write_text('{}')
    (staged/'manifest.json').write_text('{}')
    raw=sibling/'raw.bin';raw.write_bytes(b'x'*8192)
    os.link(raw,staged/'raw.bin')
    expected=sum(p.stat().st_blocks*512 for p in staged.iterdir())
    destination=tmp_path/'datasets';destination.mkdir()
    reservations=[]
    def quota(root,reserve):reservations.append(reserve);return ('capture_quota','test rejection')
    monkeypatch.setattr('carla_safety_agent.capture_quota.check_capture_quota',quota)
    with pytest.raises(ValueError,match='test rejection'):publish_capture(staged,destination)
    assert reservations==[expected]
    assert raw.read_bytes()==(staged/'raw.bin').read_bytes()


@pytest.mark.parametrize('failure',[None,'quota','busy','exists'])
def test_staged_publish_admission_preserves_rejected_copy(tmp_path,monkeypatch,failure):
    from carla_safety_agent.capture_quota import publish_capture,capture_write_lock
    from contextlib import nullcontext
    staged=tmp_path/'staging/recovered-test';staged.mkdir(parents=True)
    (staged/'manifest.json').write_text('{"run_id":"recovered-test"}')
    (staged/'raw.bin').write_bytes(b'original bytes')
    destination=tmp_path/'datasets';destination.mkdir()
    def quota(*args,**kwargs):
        assert args[1]>0
        with pytest.raises(OSError):
            with capture_write_lock(destination):pytest.fail('Publication has no lock')
        return ('capture_quota','full') if failure=='quota' else None
    monkeypatch.setattr('carla_safety_agent.capture_quota.check_capture_quota',quota)
    if failure=='exists':(destination/staged.name).mkdir()
    with capture_write_lock(destination) if failure=='busy' else nullcontext():
        if failure:
            with pytest.raises((ValueError,OSError)):publish_capture(staged,destination)
            assert (staged/'raw.bin').read_bytes()==b'original bytes'
        else:
            published=publish_capture(staged,destination)
            assert not staged.exists() and (published/'raw.bin').read_bytes()==b'original bytes'


@pytest.mark.parametrize('abrupt', [False, True])
def test_write_lock_independent_process_and_exit_release(tmp_path, abrupt):
    import os
    import select
    import subprocess
    import sys
    from pathlib import Path
    from carla_safety_agent.capture_quota import capture_write_lock
    # A fresh interpreter cannot inherit this test's lock state.
    code='''
import os, sys
from carla_safety_agent.capture_quota import capture_write_lock
with capture_write_lock(sys.argv[1]):
    print('locked', flush=True)
    command=sys.stdin.readline().strip()
    if command=='abrupt': os._exit(17)
'''
    environment=dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]/'src'))
    child=subprocess.Popen([sys.executable,'-c',code,str(tmp_path)],env=environment,
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        assert select.select([child.stdout],[],[],10)[0], 'Child did not acquire lock'
        assert child.stdout.readline().strip()=='locked'
        assert child.poll() is None
        inode=(tmp_path/'.capture-write.lock').stat().st_ino
        with pytest.raises(OSError,match='Another capture writer'):
            with capture_write_lock(tmp_path):pytest.fail('Second process entered write section')
        child.communicate('abrupt\n' if abrupt else 'release\n',timeout=10)
        assert child.returncode==(17 if abrupt else 0)
        with capture_write_lock(tmp_path):
            assert (tmp_path/'.capture-write.lock').stat().st_ino==inode
    finally:
        if child.poll() is None:
            child.kill();child.communicate(timeout=10)


def test_write_lock_conflict_release_and_persistent_inode(tmp_path):
    from carla_safety_agent.capture_quota import capture_write_lock
    with capture_write_lock(tmp_path):
        inode=(tmp_path/'.capture-write.lock').stat().st_ino
        with pytest.raises(OSError,match='Another capture writer'):
            with capture_write_lock(tmp_path):pytest.fail('Competing writer admitted')
    with pytest.raises(RuntimeError):
        with capture_write_lock(tmp_path):raise RuntimeError('Injected write failure')
    with capture_write_lock(tmp_path):
        assert (tmp_path/'.capture-write.lock').stat().st_ino==inode


def test_write_lock_refuses_symlink(tmp_path):
    from carla_safety_agent.capture_quota import capture_write_lock
    original=tmp_path/'original';original.write_text('preserve')
    (tmp_path/'.capture-write.lock').symlink_to(original)
    with pytest.raises(OSError):
        with capture_write_lock(tmp_path):pytest.fail('Linked lock admitted')
    assert original.read_text()=='preserve'


@pytest.mark.parametrize('case', ['valid','cwd','argv','default','duplicate','incomplete','small','boolean'])
def test_probe_gate_requires_explicit_bounded_configuration(case):
    from carla_safety_agent.capture_quota import verify_quota_probe
    cwd='/project'; argv=['python3','tools/livery_bridge.py']
    env=['CSA_CAPTURE_QUOTA_GIB=90']; usage={'complete':True,'allocated_bytes':91*1024**3}
    if case=='cwd': cwd='/other'
    if case=='argv': argv=['python3','other.py']
    if case=='default': env=[]
    if case=='duplicate': env*=2
    if case=='incomplete': usage['complete']=False
    if case=='small': usage['allocated_bytes']=90*1024**3
    if case=='boolean': usage['allocated_bytes']=True
    if case=='valid': verify_quota_probe('/project',cwd,argv,env,usage)
    else:
        with pytest.raises(ValueError): verify_quota_probe('/project',cwd,argv,env,usage)


def test_policy_snapshot_survives_environment_change(monkeypatch):
    from carla_safety_agent.capture_quota import capture_quota_policy
    monkeypatch.setenv('CSA_CAPTURE_QUOTA_GIB','90')
    policy = capture_quota_policy()
    monkeypatch.setenv('CSA_CAPTURE_QUOTA_GIB','200')
    assert policy['limit_bytes'] == 90*1024**3
    assert capture_quota_policy()['limit_bytes'] == 200*1024**3
    monkeypatch.setenv('CSA_CAPTURE_QUOTA_GIB','9'*5000)
    assert capture_quota_policy()['valid'] is False


def test_quota_includes_next_sample_and_exact_boundary(monkeypatch):
    monkeypatch.setattr('carla_safety_agent.capture_quota.inventory_captures',
        lambda root: {'complete':True, 'allocated_bytes':90})
    assert check_capture_quota('root',10,limit_bytes=100) is None
    assert check_capture_quota('root',11,limit_bytes=100)[0] == 'capture_quota'


def test_incomplete_scan_stops_admission(monkeypatch):
    monkeypatch.setattr('carla_safety_agent.capture_quota.inventory_captures',
        lambda root: {'complete':False, 'allocated_bytes':0})
    assert check_capture_quota('root',0,limit_bytes=100)[0] == 'quota_unknown'


@pytest.mark.parametrize('value', ['0','-1','nan','1.5','100001','１２'])
def test_invalid_configuration_fails_closed(monkeypatch,value):
    monkeypatch.setenv('CSA_CAPTURE_QUOTA_GIB',value)
    assert check_capture_quota('root',0)[0] == 'quota_unknown'


def test_missing_root_not_zero_usage(tmp_path):
    assert check_capture_quota(tmp_path/'missing',0,limit_bytes=100)[0] == 'quota_unknown'


def test_incomplete_recording_directory_blocks_real_quota_scan(tmp_path):
    folder = tmp_path/'capture-interrupted'; folder.mkdir()
    (folder/'raw.bin').write_bytes(b'raw data')
    assert check_capture_quota(tmp_path,0,limit_bytes=1024**3)[0] == 'quota_unknown'

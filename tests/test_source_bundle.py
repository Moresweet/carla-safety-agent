import json
import os
from pathlib import Path
import subprocess
import zipfile

import pytest

from carla_safety_agent.source_bundle import export_source, included, verify_source, restore_source


@pytest.fixture
def repository(tmp_path):
    root = tmp_path / 'repo'
    root.mkdir()
    def git(*args):
        return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.PIPE)
    git('init')
    git('config', 'user.email', 'fixture@example.invalid')
    git('config', 'user.name', 'Local Fixture')
    (root / 'README.md').write_text('committed source')
    (root / 'scripts').mkdir()
    (root / 'scripts/run.sh').write_text('#!/bin/sh\nexit 0\n')
    (root / 'scripts/run.sh').chmod(0o755)
    (root / 'data').mkdir()
    (root / 'data/private.txt').write_text('not included')
    git('add', '.')
    git('commit', '-m', 'fixture')
    return root, git


@pytest.mark.parametrize('change',['modified','untracked','deleted','staged'])
def test_current_export_refuses_omissions_before_writing(repository,tmp_path,change):
    root,git=repository
    if change=='untracked':(root/'scripts/new.py').write_text('print(1)')
    elif change=='deleted':(root/'README.md').unlink()
    else:
        (root/'README.md').write_text('changed')
        if change=='staged':git('add','README.md')
    output=tmp_path/'current.zip'
    with pytest.raises(ValueError,match='Current-development export refused'):
        export_source(root,output,require_current=True)
    assert not output.exists() and not list(tmp_path.glob('current.zip.partial-*'))


def test_export_status_reports_omissions_without_changing_index(repository):
    from carla_safety_agent.source_bundle import source_export_status
    root,git=repository
    assert source_export_status(root)['current_source_export_ready'] is True
    (root/'README.md').write_text('local edit')
    (root/'scripts/new.py').write_text('new source')
    (root/'data/new-private.txt').write_text('excluded')
    before=git('status','--porcelain=v1')
    index=(root/'.git/index').read_bytes()
    result=source_export_status(root)
    assert result['current_source_export_ready'] is False
    assert result['uncommitted_source_omitted']==['README.md','scripts/new.py']
    assert result['omitted_source_count']==2
    assert (root/'.git/index').read_bytes()==index
    assert git('status','--porcelain=v1')==before


def test_current_export_accepts_clean_selected_source(repository,tmp_path):
    root,_=repository
    (root/'data/untracked.txt').write_text('excluded runtime')
    result=export_source(root,tmp_path/'current.zip',require_current=True)
    assert not result['uncommitted_source_omitted']


@pytest.mark.parametrize('change',['worktree','commit'])
def test_strict_export_rechecks_before_publication(repository,tmp_path,monkeypatch,change):
    import carla_safety_agent.source_bundle as module
    root,git=repository
    original=module.verify_source
    def verify_then_change(path):
        result=original(path)
        (root/'README.md').write_text('changed during export')
        if change=='commit':
            git('add','README.md');git('commit','-m','concurrent change')
        return result
    monkeypatch.setattr(module,'verify_source',verify_then_change)
    output=tmp_path/'current.zip'
    with pytest.raises(RuntimeError,match='changed during export'):
        export_source(root,output,require_current=True)
    assert not output.exists()
    assert len(list(tmp_path.glob('current.zip.partial-*')))==1


def test_source_snapshot_uses_commit_not_dirty_files(repository, tmp_path):
    root, git = repository
    (root / 'README.md').write_text('uncommitted change')
    (root / 'scripts/untracked.sh').write_text('not included')
    output = tmp_path / 'source.zip'
    result = export_source(root, output)
    assert result['files'] == 2 and result['omitted'] == ['data/private.txt']
    assert result['commit'] == git('rev-parse', 'HEAD').decode().strip()
    assert result['uncommitted_source_omitted'] == ['README.md', 'scripts/untracked.sh']
    assert result['has_omitted_uncommitted_source'] is True and result['warnings']
    verified = verify_source(output)
    assert verified['ok']
    assert verified['uncommitted_source_omitted'] == result['uncommitted_source_omitted']
    assert verified['warnings']
    with zipfile.ZipFile(output) as archive:
        assert archive.read('source/README.md') == b'committed source'
        assert archive.getinfo('source/scripts/run.sh').external_attr >> 16 == 0o100755
    original = output.read_bytes()
    with pytest.raises(ValueError, match='already exists'):
        export_source(root, output)
    assert output.read_bytes() == original


def test_clean_source_does_not_warn_about_unrelated_private_untracked_files(repository, tmp_path):
    root, _ = repository
    (root / 'data/local-secret.txt').write_text('not source')
    result = export_source(root, tmp_path / 'clean.zip')
    assert result['uncommitted_source_omitted'] == []
    assert result['has_omitted_uncommitted_source'] is False
    assert result['warnings'] == []


@pytest.mark.parametrize('value', [None, ['../escape'], ['README.md', 'README.md'], 'bad'])
def test_invalid_persisted_omissions_rejected(repository, tmp_path, value):
    root, _ = repository
    original, altered = tmp_path / 'source.zip', tmp_path / 'altered.zip'
    export_source(root, original)
    with zipfile.ZipFile(original) as before, zipfile.ZipFile(altered, 'w') as after:
        for info in before.infolist():
            data = before.read(info)
            if info.filename == 'manifest.json':
                document = json.loads(data)
                document['uncommitted_source_omitted'] = value
                data = json.dumps(document).encode()
            after.writestr(info, data)
    with pytest.raises(ValueError, match='omission list'):
        verify_source(altered)


def test_legacy_archive_reports_unknown_omissions(repository, tmp_path):
    root, _ = repository
    original, legacy = tmp_path / 'source.zip', tmp_path / 'legacy.zip'
    export_source(root, original)
    with zipfile.ZipFile(original) as before, zipfile.ZipFile(legacy, 'w') as after:
        for info in before.infolist():
            data = before.read(info)
            if info.filename == 'manifest.json':
                document = json.loads(data)
                del document['uncommitted_source_omitted']
                data = json.dumps(document).encode()
            after.writestr(info, data)
    result = verify_source(legacy)
    assert result['ok'] and result['uncommitted_source_omitted'] is None
    assert not result['uncommitted_source_inventory_recorded'] and result['warnings']


def test_restore_roundtrip_to_new_directory_only(repository, tmp_path):
    root, _ = repository
    (root / 'README.md').write_text('not committed')
    archive, destination = tmp_path / 'snapshot.zip', tmp_path / 'restored'
    export_source(root, archive)
    result = restore_source(archive, destination)
    assert (destination / 'README.md').read_text() == 'committed source'
    assert (destination / 'scripts/run.sh').stat().st_mode & 0o777 == 0o755
    assert not (destination / 'data').exists()
    assert result['warnings'] and not result['code_executed']
    assert not result['git_repository_restored'] and not result['runtime_verified']
    assert json.loads((destination / 'SOURCE_RESTORE_RECEIPT.json').read_text())['warnings']
    with pytest.raises(ValueError, match='must not exist'):
        restore_source(archive, destination)


def test_invalid_restore_creates_no_destination(tmp_path):
    source, target = tmp_path / 'bad.zip', tmp_path / 'restore'
    source.write_bytes(b'invalid archive')
    with pytest.raises(zipfile.BadZipFile): restore_source(source, target)
    assert not target.exists()


def test_restore_command_roundtrip_and_existing_destination_rejection(repository, tmp_path):
    root, _ = repository
    archive, target = tmp_path / 'cli.zip', tmp_path / 'cli-restored'
    export_source(root, archive)
    project = Path(__file__).resolve().parents[1]
    command = ['python3', str(project / 'tools/source_bundle.py'), 'restore', str(archive),
               '--destination', str(target)]
    env = {**os.environ, 'PYTHONPATH': str(project / 'src')}
    completed = subprocess.run(command, env=env, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result['ok'] and not result['runtime_verified']
    assert (target / 'README.md').read_text() == 'committed source'
    repeated = subprocess.run(command, env=env, capture_output=True, text=True)
    assert repeated.returncode != 0 and 'must not exist' in repeated.stderr


@pytest.mark.parametrize('path', ['../src/a.py', '/src/a.py', 'src/../a.py', 'src/.env',
    'tools/node_modules/a.js', 'src/weights.ckpt', 'scripts/key.pem', '.git/config', 'data/a.py',
    'tools/.openai/hosting.json', 'tools/x\\a.py'])
def test_excluded_paths(path):
    assert not included(path)


@pytest.mark.parametrize('mutation', ['bytes', 'extra', 'mode', 'duplicate_json'])
def test_tampered_source_is_rejected(repository, tmp_path, mutation):
    root, _ = repository
    source, target = tmp_path / 'source.zip', tmp_path / 'tampered.zip'
    export_source(root, source)
    with zipfile.ZipFile(source) as before, zipfile.ZipFile(target, 'w') as after:
        for info in before.infolist():
            data = before.read(info)
            if info.filename == 'source/README.md':
                if mutation == 'bytes':
                    data = b'wrong source'
                if mutation == 'mode':
                    info.external_attr = 0o120777 << 16
            if info.filename == 'manifest.json' and mutation == 'duplicate_json':
                data = data[:-1] + b',"commit":"fake"}'
            after.writestr(info, data)
        if mutation == 'extra':
            after.writestr('source/extra.py', 'extra')
    with pytest.raises(ValueError):
        verify_source(target)


def test_tracked_symlink_is_not_packaged(repository, tmp_path):
    root, git = repository
    (root / 'scripts/link').symlink_to('/etc/passwd')
    git('add', 'scripts/link')
    git('commit', '-m', 'link')
    with pytest.raises(ValueError, match='regular Git blob'):
        export_source(root, tmp_path / 'source.zip')

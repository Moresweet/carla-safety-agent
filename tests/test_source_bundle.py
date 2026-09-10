import json
from pathlib import Path
import subprocess
import zipfile

import pytest

from carla_safety_agent.source_bundle import export_source, included, verify_source


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


def test_source_snapshot_uses_commit_not_dirty_files(repository, tmp_path):
    root, git = repository
    (root / 'README.md').write_text('uncommitted change')
    (root / 'scripts/untracked.sh').write_text('not included')
    output = tmp_path / 'source.zip'
    result = export_source(root, output)
    assert result['files'] == 2 and result['omitted'] == ['data/private.txt']
    assert result['commit'] == git('rev-parse', 'HEAD').decode().strip()
    assert verify_source(output)['ok']
    with zipfile.ZipFile(output) as archive:
        assert archive.read('source/README.md') == b'committed source'
        assert archive.getinfo('source/scripts/run.sh').external_attr >> 16 == 0o100755
    original = output.read_bytes()
    with pytest.raises(ValueError, match='already exists'):
        export_source(root, output)
    assert output.read_bytes() == original


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

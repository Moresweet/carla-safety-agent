"""Bounded committed-source snapshots. No execution, installation or Git network."""
import hashlib
import io
import json
import os
import re
import stat
from pathlib import Path, PurePosixPath
import subprocess
import time
import uuid
import zipfile

SCHEMA = 'carla-source-bundle/1'
MAX_BYTES = 256 * 1024 * 1024
MAX_FILE = 32 * 1024 * 1024
ROOTS = {'src', 'tools', 'scripts', 'tests', 'docs', 'integration', 'ros2', 'schema'}
ROOT_FILES = {'README.md', 'pyproject.toml', '.gitignore'}
BLOCKED = {'.git', '.runtime', '.codex', '.agents', '.openai', 'node_modules', '__pycache__',
           'data', 'runs', 'dist', '.next', '.venv', 'ckpts', 'checkpoints', '.env'}


def included(name):
    path = PurePosixPath(name)
    if (not name or path.is_absolute() or str(path) != name or
            any(part in ('.', '..') or part in BLOCKED or part.startswith('.env.') for part in path.parts)
            or any(ord(c) < 32 for c in name) or '\\' in name or ':' in name):
        return False
    if path.suffix.lower() in {'.pth', '.ckpt', '.pt', '.safetensors', '.blend', '.fbx', '.uasset', '.pem', '.key'}:
        return False
    return name in ROOT_FILES or path.parts[0] in ROOTS


def _git(project, *args):
    return subprocess.check_output(['git', '-C', str(project), *args], timeout=10,
                                   stderr=subprocess.PIPE)


def uncommitted_source(project, commit):
    # Inspect names only; never read uncommitted secrets into the archive.
    changed = _git(project, 'diff', '--name-only', '-z', commit, '--').split(b'\0')
    untracked = _git(project, 'ls-files', '--others', '--exclude-standard', '-z').split(b'\0')
    return sorted({name.decode('utf-8') for name in changed + untracked
                              if name and included(name.decode('utf-8'))})


def source_export_status(project):
    """Read-only admission evidence; does not stage, commit or export files."""
    project=Path(project)
    commit=_git(project,'rev-parse','--verify','HEAD^{commit}').decode().strip()
    changes=uncommitted_source(project,commit)
    return {'schema_version':'source-export-status/1','commit':commit,
            'current_source_export_ready':not changes,'omitted_source_count':len(changes),
            'uncommitted_source_omitted':changes,
            'scope':'Selected committed source only; not dependencies, runtime data or cross-machine readiness'}


def export_source(project, output, *, require_current=False):
    project, output = Path(project), Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError('Source bundle output already exists')
    commit = _git(project, 'rev-parse', '--verify', 'HEAD^{commit}').decode().strip()
    omitted_worktree = uncommitted_source(project, commit)
    if require_current and omitted_worktree:
        raise ValueError('Current-development export refused: uncommitted source would be omitted: '
                         + ', '.join(omitted_worktree[:20])
                         + (f' (+{len(omitted_worktree)-20} more)' if len(omitted_worktree)>20 else ''))
    tree = _git(project, 'ls-tree', '-rlz', commit)
    entries, omitted = [], []
    for record in tree.split(b'\0'):
        if not record:
            continue
        metadata, raw_name = record.split(b'\t', 1)
        name = raw_name.decode('utf-8')
        mode, kind, oid, size = metadata.decode().split()
        if not included(name):
            omitted.append(name)
            continue
        if kind != 'blob' or mode not in ('100644', '100755'):
            raise ValueError('Selected source must be a regular Git blob: ' + name)
        if not 0 <= int(size) <= MAX_FILE:
            raise ValueError('Selected source exceeds per-file limit: ' + name)
        entries.append((name, mode, oid, int(size)))
    if not entries or len(entries) > 5000 or sum(row[3] for row in entries) > MAX_BYTES:
        raise ValueError('Empty or oversized committed source snapshot')
    manifest = {'schema_version': SCHEMA, 'commit': commit, 'files': {}, 'omitted': omitted,
                'uncommitted_source_omitted': omitted_worktree,
                'scope': 'Committed source only; uncommitted edits, runtime state and dependencies are not included'}
    temporary = output.with_name(output.name + '.partial-' + uuid.uuid4().hex)
    started = time.monotonic()
    try:
        with temporary.open('xb') as stream:
            with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                for name, mode, oid, size in entries:
                    if time.monotonic() - started > 120:
                        raise TimeoutError('Source export exceeded 120 seconds')
                    data = _git(project, 'cat-file', 'blob', oid)
                    if len(data) != size or data.startswith(b'version https://git-lfs.github.com/spec/v1\n'):
                        raise ValueError('Missing source bytes or unresolved LFS pointer: ' + name)
                    info = zipfile.ZipInfo('source/' + name)
                    info.create_system = 3
                    info.external_attr = int(mode, 8) << 16
                    info.compress_type = zipfile.ZIP_DEFLATED
                    archive.writestr(info, data)
                    manifest['files'][name] = {'size': size, 'sha256': hashlib.sha256(data).hexdigest(), 'mode': mode}
                archive.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, sort_keys=True))
            stream.flush()
            os.fsync(stream.fileno())
        verify_source(temporary)
        if require_current:
            current_commit = _git(project, 'rev-parse', '--verify', 'HEAD^{commit}').decode().strip()
            if current_commit != commit or uncommitted_source(project, commit):
                raise ValueError('Selected source changed during export; refusing publication')
        os.link(temporary, output)  # Publish without ever replacing another file.
        directory = os.open(output.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        temporary.unlink()
    except BaseException as exc:
        raise RuntimeError(f'Source export not confirmed; inspect {temporary} and {output}: {exc}') from exc
    return {'ok': True, 'archive': str(output.resolve()), 'commit': commit,
            'files': len(entries), 'source_bytes': sum(row[3] for row in entries),
            'omitted': omitted, 'runtime_verified': False,
            'uncommitted_source_omitted': omitted_worktree,
            'has_omitted_uncommitted_source': bool(omitted_worktree),
            'warnings': (['Source archive excludes current uncommitted source changes; '
                          'it is a committed snapshot, not a backup of current development.']
                         if omitted_worktree else [])}


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate source manifest field')
        result[key] = value
    return result


def verify_source(path):
    size = len(path.getbuffer()) if isinstance(path, io.BytesIO) else Path(path).stat().st_size
    if size > MAX_BYTES + 8 * 1024 * 1024:
        raise ValueError('Oversized source archive')
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if len(names) > 5001 or len(set(names)) != len(names) or 'manifest.json' not in names:
            raise ValueError('Invalid source archive members')
        if sum(info.file_size for info in infos) > MAX_BYTES + 4 * 1024 * 1024:
            raise ValueError('Oversized unpacked source archive')
        if archive.getinfo('manifest.json').file_size > 4 * 1024 * 1024:
            raise ValueError('Oversized source manifest')
        manifest = json.loads(archive.read('manifest.json'), object_pairs_hook=_unique_pairs)
        required = {'schema_version', 'commit', 'files', 'omitted', 'scope'}
        if (not isinstance(manifest, dict) or not required <= set(manifest)
                or set(manifest) - required - {'uncommitted_source_omitted'}
                or manifest.get('schema_version') != SCHEMA or not isinstance(manifest.get('files'), dict)
                or not isinstance(manifest['commit'], str) or not re.fullmatch(r'(?:[a-f0-9]{40}|[a-f0-9]{64})', manifest['commit'])
                or not isinstance(manifest['omitted'], list) or any(not isinstance(v, str) for v in manifest['omitted'])):
            raise ValueError('Invalid source manifest')
        omitted_worktree = manifest.get('uncommitted_source_omitted')
        if 'uncommitted_source_omitted' in manifest:
            if (not isinstance(omitted_worktree, list)
                    or any(not isinstance(name, str) or not included(name) for name in omitted_worktree)
                    or len(set(omitted_worktree)) != len(omitted_worktree)):
                raise ValueError('Invalid uncommitted source omission list')
        files = manifest['files']
        if not files or set(names) != {'manifest.json', *('source/' + name for name in files)}:
            raise ValueError('Source members do not match manifest')
        for name, record in files.items():
            if not included(name) or not isinstance(record, dict) or set(record) != {'size', 'sha256', 'mode'}:
                raise ValueError('Invalid source reference')
            if type(record['size']) is not int or not 0 <= record['size'] <= MAX_FILE or record['mode'] not in ('100644', '100755'):
                raise ValueError('Invalid source size or mode')
            info = archive.getinfo('source/' + name)
            mode = info.external_attr >> 16
            if (stat.S_IFMT(mode) != stat.S_IFREG or stat.S_IMODE(mode) != int(record['mode'], 8) & 0o777
                    or info.flag_bits & 1):
                raise ValueError('Invalid source archive mode: ' + name)
            if info.file_size != record['size']:
                raise ValueError('Source size mismatch: ' + name)
            data = archive.read(info)
            if hashlib.sha256(data).hexdigest() != record['sha256']:
                raise ValueError('Source checksum mismatch: ' + name)
    return {'ok': True, 'commit': manifest.get('commit'), 'files': len(files),
            'uncommitted_source_omitted': omitted_worktree,
            'uncommitted_source_inventory_recorded': omitted_worktree is not None,
            'warnings': (['Legacy archive: uncommitted source omissions were not recorded.']
                         if omitted_worktree is None else
                         ['Archive omits uncommitted source changes; not a current-development backup.']
                         if omitted_worktree else []),
            'runtime_verified': False, 'code_executed': False}


def restore_source(path, destination):
    """Restore verified committed source into a new directory, never execute it.

    Validate an immutable bounded in-memory snapshot so a changed archive path
    cannot swap different content between verification and extraction.
    """
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError('Restore destination must not exist')
    with Path(path).open('rb') as stream:
        data = stream.read(MAX_BYTES + 8 * 1024 * 1024 + 1)
    snapshot = io.BytesIO(data)
    verified = verify_source(snapshot)
    snapshot.seek(0)
    destination.mkdir()  # Never merge with an existing project, even an empty one.
    try:
        with zipfile.ZipFile(snapshot) as archive:
            manifest = json.loads(archive.read('manifest.json'), object_pairs_hook=_unique_pairs)
            for name, record in manifest['files'].items():
                target = destination / name
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open('xb') as output:
                    output.write(archive.read('source/' + name))
                target.chmod(int(record['mode'], 8) & 0o777)
            # Keep provenance outside the source list; never imply a Git repo
            # or dependencies were restored by extracting plain source files.
            with (destination / 'SOURCE_RESTORE_RECEIPT.json').open('x') as output:
                json.dump(verified, output, ensure_ascii=False, indent=2)
    except BaseException as error:
        raise RuntimeError(f'Incomplete source restore retained at {destination}: {error}') from error
    return {**verified, 'destination': str(destination.resolve()), 'git_repository_restored': False}

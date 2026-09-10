"""Bounded committed-source snapshots. No execution, installation or Git network."""
import hashlib
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


def export_source(project, output):
    project, output = Path(project), Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError('Source bundle output already exists')
    commit = _git(project, 'rev-parse', '--verify', 'HEAD^{commit}').decode().strip()
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
            'omitted': omitted, 'runtime_verified': False}


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate source manifest field')
        result[key] = value
    return result


def verify_source(path):
    if Path(path).stat().st_size > MAX_BYTES + 8 * 1024 * 1024:
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
        if (not isinstance(manifest, dict) or set(manifest) != {'schema_version', 'commit', 'files', 'omitted', 'scope'}
                or manifest.get('schema_version') != SCHEMA or not isinstance(manifest.get('files'), dict)
                or not isinstance(manifest['commit'], str) or not re.fullmatch(r'(?:[a-f0-9]{40}|[a-f0-9]{64})', manifest['commit'])
                or not isinstance(manifest['omitted'], list) or any(not isinstance(v, str) for v in manifest['omitted'])):
            raise ValueError('Invalid source manifest')
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
            'runtime_verified': False, 'code_executed': False}

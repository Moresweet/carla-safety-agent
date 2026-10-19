"""Immutable local copies of explicitly registered, metadata-verified splits."""
import hashlib
import json
import os
from pathlib import Path
import uuid
import fcntl
import stat
from contextlib import contextmanager

from .capture_references import split_references
from .dataset_split import verify_saved_split
from .scene_store import read_json

LIMIT = 8 * 1024**2


class SplitRegistryBusy(RuntimeError):
    """A cooperating registration or cleanup currently holds the registry."""


def encoded_split(document):
    return json.dumps(document, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()


def register_split(source, registry, dataset_root):
    with registry_mutation_lock(registry):
        return _register_split(source, registry, dataset_root)


@contextmanager
def registry_mutation_lock(registry):
    """Cooperating registration/cleanup processes share a fail-fast lock.

    Keep this held from verification through publication, or from the final
    reference check through removal. Never unlink the persistent lock inode.
    """
    root = Path(registry)
    if root.is_symlink():
        raise ValueError('Split registry must not be linked')
    root.parent.mkdir(parents=True, exist_ok=True)
    path = root.with_name(root.name + '.lock')
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError('Split registry lock must be a regular file')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SplitRegistryBusy('Split registration or cleanup is busy; retry explicitly') from exc
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _register_split(source, registry, dataset_root):
    document = read_json(Path(source), max_bytes=LIMIT)
    return _register_document(document, registry, dataset_root)


def register_split_payload(payload, registry, dataset_root):
    """Register uploaded JSON, never a client-supplied filesystem path."""
    if not isinstance(payload, bytes) or not payload or len(payload) > LIMIT:
        raise ValueError('Split upload must be nonempty JSON within 8 MiB')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate split JSON key')
            result[key] = value
        return result
    def constant(value):
        raise ValueError('Nonfinite split JSON number')
    try:
        document = json.loads(payload, object_pairs_hook=pairs, parse_constant=constant)
        encoded_split(document)  # Reject overflow floats before acquiring the lock.
    except RecursionError as exc:
        raise ValueError('Split JSON nesting exceeds supported depth') from exc
    with registry_mutation_lock(registry):
        return _register_document(document, registry, dataset_root)


def _register_document(document, registry, dataset_root):
    verification = verify_saved_split(document, dataset_root)
    if not verification['run_count']:
        raise ValueError('Cannot register an empty split')
    payload = encoded_split(document)
    if len(payload) > LIMIT:
        raise ValueError('Split exceeds registry size limit')
    root = Path(registry)
    if root.is_symlink():
        raise ValueError('Split registry must not be linked')
    root.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(payload).hexdigest()
    target = root / (digest + '.json')
    temporary = root / (digest + '.' + uuid.uuid4().hex + '.partial')
    created = False
    try:
        with temporary.open('xb') as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, target)
            created = True
        except FileExistsError:
            if encoded_split(read_json(target, max_bytes=LIMIT)) != payload:
                raise ValueError('Existing registered split changed; refusing overwrite')
        descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        temporary.unlink(missing_ok=True)
    return {'ok': True, 'created': created, 'sha256': digest, 'path': str(target.absolute()), **verification}


def registered_split_references(registry, *, max_files=500):
    """Preserve detected references even if a registered file's hash is wrong.

    Missing registry means no registrations, not no external splits. Never
    turn unreadable or partially published entries into an empty safe result.
    """
    if type(max_files) is not int or max_files < 1:
        raise ValueError('max_files must be positive')
    root = Path(registry)
    result = {'references': {}, 'complete': True, 'warnings': [], 'scanned_files': 0,
              'scope': 'Registered local splits only; external unregistered splits are not scanned; not deletion approval'}
    if not root.exists() and not root.is_symlink():
        return result
    if root.is_symlink() or not root.is_dir():
        result.update(complete=False, warnings=['Split registry missing or unsafe'])
        return result
    for count, path in enumerate(sorted(root.iterdir())):
        if count >= max_files:
            result['warnings'].append('Registered split scan limit reached')
            break
        partial = split_references([path])
        result['scanned_files'] += 1
        result['warnings'].extend(partial['warnings'])
        for run, references in partial['references'].items():
            result['references'].setdefault(run, []).extend(references)
        try:
            document = read_json(path, max_bytes=LIMIT)
            expected = hashlib.sha256(encoded_split(document)).hexdigest() + '.json'
            if path.name != expected:
                raise ValueError('Registered split content hash/name mismatch or unfinished entry')
        except (OSError, ValueError, RecursionError) as exc:
            result['warnings'].append(f'{path.name}: {exc}')
    result['complete'] = not result['warnings']
    return result


def require_no_registered_split_references(registry, run_ids):
    result = registered_split_references(registry)
    if not result['complete']:
        raise ValueError('Registered split reference scan incomplete; cleanup refused')
    referenced = sorted(set(run_ids) & result['references'].keys())
    if referenced:
        raise ValueError('Registered split still references recordings: ' + ', '.join(referenced))
    return result  # Only this reference category checked, never deletion approval.

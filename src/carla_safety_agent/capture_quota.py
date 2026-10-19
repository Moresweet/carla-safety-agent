"""Conservative recording admission; never deletes data to make room."""
import os
import fcntl
from contextlib import contextmanager
from pathlib import Path
from .capture_storage import inventory_captures


@contextmanager
def capture_write_lock(root):
    """Serialize cooperating SensorCapture admission and sample writes.

    Nonblocking: a competing writer stops recording instead of stalling tick.
    Other tools and external writers are not covered by this advisory lock.
    Never unlink the lock file: doing so would split its inode/lock identity.
    """
    root=Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('Capture write root must be a real directory')
    descriptor=os.open(root/'.capture-write.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    with os.fdopen(descriptor,'r+') as stream:
        try:
            fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise OSError('Another capture writer holds admission lock; recording stopped without waiting') from error
        try:yield
        finally:fcntl.flock(stream,fcntl.LOCK_UN)


def verify_quota_probe(root, cwd, argv, environment, usage):
    """Fail closed before the opt-in 90 GiB real regression starts a worker."""
    from pathlib import Path
    if Path(cwd) != Path(root) or 'tools/livery_bridge.py' not in argv:
        raise ValueError('Quota test bridge identity mismatch')
    values = [item for item in environment if item.startswith('CSA_CAPTURE_QUOTA_GIB=')]
    if values != ['CSA_CAPTURE_QUOTA_GIB=90']:
        raise ValueError('Quota test requires explicit 90 GiB bridge configuration')
    if (not isinstance(usage,dict) or usage.get('complete') is not True
            or type(usage.get('allocated_bytes')) is not int
            or usage['allocated_bytes'] <= 90*1024**3):
        raise ValueError('Quota test requires complete measurement already above 90 GiB')


def publish_capture(staged, destination_root):
    """Admit an already audited staged folder under the recording writer lock.

    On rejection the staging copy is retained. Staging and ZIP disk usage are
    outside the capture-root policy; this is not a whole-runtime disk quota.
    """
    staged=Path(staged);destination_root=Path(destination_root)
    if staged.is_symlink() or not staged.is_dir():raise ValueError('Invalid staged capture')
    destination=destination_root/staged.name
    if staged.resolve()==destination.resolve():raise ValueError('Capture is already published')
    with capture_write_lock(destination_root):
        if destination.exists() or destination.is_symlink():raise ValueError('Capture destination already exists')
        measured=inventory_captures(staged.parent,only_directory=staged.name)
        row=next((r for r in measured['recordings'] if r['directory']==staged.name),None)
        if row is None or not row['measurement_complete']:raise ValueError('Staged capture size could not be measured')
        quota=check_capture_quota(destination_root,row['allocated_bytes'])
        if quota is not None:raise ValueError(quota[1]+'; staged copy retained')
        staged.rename(destination)
    return destination


def capture_quota_policy():
    raw = os.environ.get('CSA_CAPTURE_QUOTA_GIB', '100')
    valid = raw.isascii() and raw.isdigit() and len(raw) <= 6 and 1 <= int(raw) <= 100000
    return {'schema_version':'capture-quota-policy/1', 'valid':valid,
            'limit_bytes':int(raw)*1024**3 if valid else None,
            'source':'environment' if 'CSA_CAPTURE_QUOTA_GIB' in os.environ else 'default',
            'measurement':'allocated_file_blocks_in_manifest_directories',
            'scope':'Capture root only; not an atomic filesystem quota'}


def check_capture_quota(root, reserve, *, limit_bytes=None):
    """Check current capture file blocks before admitting another sample.

    This is not a filesystem quota: external/concurrent writers may race the
    observation. Archive files outside this root are not included.
    """
    if type(reserve) is not int or reserve < 0:
        raise ValueError('Invalid sample reservation')
    if limit_bytes is None:
        policy = capture_quota_policy()
        if not policy['valid']:
            return 'quota_unknown', 'Invalid CSA_CAPTURE_QUOTA_GIB; recording admission stopped'
        limit_bytes = policy['limit_bytes']
    if type(limit_bytes) is not int or limit_bytes <= 0:
        raise ValueError('Invalid capture quota')
    try:
        result = inventory_captures(root)
    except (ValueError, OSError) as error:
        return 'quota_unknown', f'Capture quota could not be measured: {error}'
    if not result['complete']:
        return 'quota_unknown', 'Capture quota measurement incomplete; existing samples preserved'
    if result['allocated_bytes'] + reserve > limit_bytes:
        return 'capture_quota', 'Capture directory quota reached before next sample; existing samples preserved'
    return None

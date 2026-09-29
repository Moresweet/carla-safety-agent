"""Read-only runtime accounting, including staging and logs outside captures."""
import os
import stat
import threading
from pathlib import Path

_scan_lock = threading.Lock()


class RuntimeStorageBusy(ValueError):
    pass


def review_runtime(root):
    """Single scan per bridge process; do not queue duplicate user requests."""
    if not _scan_lock.acquire(blocking=False):
        raise RuntimeStorageBusy('Runtime storage scan already running')
    try:
        return inventory_runtime(root)
    finally:
        _scan_lock.release()


def inventory_runtime(root):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('Runtime root must be a real directory')
    rows, warnings, seen = {}, [], set()
    def visit(directory, category=None):
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    group = category or entry.name
                    row = rows.setdefault(group, {'name': group, 'allocated_bytes': 0,
                        'logical_bytes': 0, 'files': 0, 'links_skipped': 0})
                    try:
                        metadata = entry.stat(follow_symlinks=False)
                        if stat.S_ISLNK(metadata.st_mode):
                            row['links_skipped'] += 1
                            warnings.append(f'Symlink excluded: {Path(entry.path).relative_to(root)}')
                        elif stat.S_ISDIR(metadata.st_mode):
                            visit(entry.path, group)
                        elif stat.S_ISREG(metadata.st_mode):
                            identity = (metadata.st_dev, metadata.st_ino)
                            row['files'] += 1
                            if identity not in seen:
                                seen.add(identity)
                                row['allocated_bytes'] += metadata.st_blocks * 512
                                row['logical_bytes'] += metadata.st_size
                        else:
                            warnings.append(f'Special file excluded: {Path(entry.path).relative_to(root)}')
                    except OSError as exc:
                        warnings.append(f'{Path(entry.path).relative_to(root)}: {exc}')
        except OSError as exc:
            warnings.append(f'{directory}: {exc}')
    visit(root)
    return {'schema_version': 'runtime-storage/1', 'root': str(root.resolve()),
        'complete': not warnings, 'warnings': warnings,
        'allocated_bytes': sum(row['allocated_bytes'] for row in rows.values()),
        'categories': sorted(rows.values(), key=lambda row: (-row['allocated_bytes'], row['name'])),
        'scope': 'Regular file blocks only; hardlinks counted once, attributed to first observed category. '
                 'No link traversal; directory metadata excluded. Live observation, not atomic quota or deletion approval.',
        'deletion_approved': False}

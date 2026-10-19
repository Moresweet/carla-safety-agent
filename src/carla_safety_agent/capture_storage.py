"""Read-only, bounded inventory of capture files; never follows symlinks."""
import json
import os
from pathlib import Path
import stat
import time


def inventory_captures(root, *, max_files=1_000_000, max_seconds=30, only_directory=None):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('Capture root must be a real directory')
    if only_directory is not None:
        from .scene_store import identifier
        identifier(only_directory)
    if type(max_files) is not int or max_files < 1:
        raise ValueError('max_files must be a positive integer')
    if type(max_seconds) not in (int, float) or not 0 < max_seconds <= 120:
        raise ValueError('max_seconds must be in (0, 120]')
    started = time.monotonic()
    rows, warnings, seen = [], [], set()
    count = 0
    exhausted = False
    folders=[root/only_directory] if only_directory is not None else sorted(root.iterdir())
    for folder in folders:
        if folder.is_symlink():
            warnings.append('Skipped linked root entry: ' + folder.name)
            continue
        if not folder.is_dir():
            if only_directory is not None:warnings.append('Selected capture directory missing: '+folder.name)
            continue
        manifest = folder/'manifest.json'
        if not manifest.exists() and not manifest.is_symlink():
            if only_directory is not None or folder.name.startswith(('capture-', 'recovered-', 'excerpt-')):
                warnings.append('Recording directory missing manifest: ' + folder.name)
            continue
        row = {'directory': folder.name, 'status': None, 'model': None,
               'execution_id': None, 'declared_bytes': None, 'frame_count': None,
               'logical_bytes': 0, 'allocated_bytes': 0, 'files': 0, 'warnings': []}
        try:
            if manifest.is_symlink() or manifest.stat().st_size > 8*1024**2:
                raise ValueError('Unsafe or oversized manifest')
            data = json.loads(manifest.read_text())
            if not isinstance(data, dict): raise ValueError('Manifest must be an object')
            for key in ('status', 'model', 'execution_id', 'frame_count'):
                row[key] = data.get(key)
            row['declared_bytes'] = data.get('bytes')
        except (OSError, ValueError) as error:
            row['warnings'].append('Manifest: ' + str(error))
        stack = [folder]
        while stack and not exhausted:
            directory = stack.pop()
            try:
                with os.scandir(directory) as entries:
                    for entry in entries:
                        if count >= max_files or time.monotonic()-started >= max_seconds:
                            exhausted = True
                            break
                        info = entry.stat(follow_symlinks=False)
                        if stat.S_ISLNK(info.st_mode):
                            row['warnings'].append('Skipped symlink: ' + str(Path(entry.path).relative_to(folder)))
                        elif stat.S_ISDIR(info.st_mode):
                            stack.append(Path(entry.path))
                        elif stat.S_ISREG(info.st_mode):
                            count += 1
                            row['files'] += 1
                            row['logical_bytes'] += info.st_size
                            identity = (info.st_dev, info.st_ino)
                            if identity not in seen:
                                seen.add(identity)
                                row['allocated_bytes'] += info.st_blocks * 512
                        else:
                            row['warnings'].append('Skipped special file: ' + entry.name)
            except OSError as error:
                row['warnings'].append('Scan: ' + str(error))
        row['measurement_complete'] = not exhausted and not row['warnings']
        rows.append(row)
        if exhausted:
            warnings.append('Scan budget reached; later directories omitted and final row may be partial')
            break
    return {'schema_version': 'capture-storage-inventory/1', 'root': str(root.resolve()),
            'only_directory':only_directory,
            'recordings': rows, 'scanned_files': count,
            'allocated_bytes': sum(row['allocated_bytes'] for row in rows),
            'complete': not warnings and all(row['measurement_complete'] for row in rows),
            'warnings': warnings, 'elapsed_s': time.monotonic()-started,
            'limitations': ['Only immediate directories with manifest.json; not total project usage',
                'File blocks only; directory metadata excluded; hard links counted once globally',
                'Live files can change during scan; this is not an atomic snapshot or deletion approval',
                'recording status alone does not prove a worker is alive; no automatic cleanup']}

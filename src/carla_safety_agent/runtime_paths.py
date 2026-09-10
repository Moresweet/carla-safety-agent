"""Read-only filesystem prerequisites; never imports native/model packages."""
import os
from pathlib import Path
import time


def diagnose_paths(environment, scope='all'):
    if scope not in ('native', 'all'):
        raise ValueError('Unknown runtime path scope')
    keys = {'UE4_EDITOR': 'executable', 'CARLA_PROJECT': 'file',
            'CARLA_PYTHONPATH': 'directory'}
    if scope == 'all':
        keys.update(UE4_EDITOR_CMD='executable', BLENDER_BIN='executable',
                    UNIAD_PYTHON='executable', E2E_ROOT='directory')
    checks = []
    for key, kind in keys.items():
        value = environment.get(key)
        row = {'variable': key, 'kind': kind, 'path': value, 'state': 'missing_configuration'}
        if isinstance(value, str) and value:
            if not Path(value).is_absolute() or any(ord(c) < 32 for c in value):
                row['state'] = 'invalid_path'
            else:
                try:
                    path = Path(value)
                    present = path.is_dir() if kind == 'directory' else path.is_file()
                    row['state'] = ('present' if present else 'missing')
                    if present and kind == 'executable' and not os.access(path, os.X_OK):
                        row['state'] = 'not_executable'
                except OSError as error:
                    row.update(state='unavailable', error=str(error))
        checks.append(row)
    return {'schema_version': 'carla-runtime-paths/1', 'observed_at': time.time(),
            'paths_present': all(row['state'] == 'present' for row in checks),
            'checks': checks, 'runtime_verified': False, 'scope': scope,
            'not_checked': ['Python ABI and imports', 'CUDA and GPU', 'engine patches and build',
                            'model file hashes and inference', 'CARLA world and asset registration'],
            'code_executed': False, 'world_modified': False}

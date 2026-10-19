"""Explicit server-side development opt-in; never changes public model status."""
import os
from pathlib import Path


def experimental_model_enabled(identifier):
    flags = {'thinktwice': 'CSA_EXPERIMENTAL_THINKTWICE',
             'driveadapter': 'CSA_EXPERIMENTAL_DRIVEADAPTER'}
    return isinstance(identifier, str) and identifier in flags and os.environ.get(flags[identifier]) == '1'


def require_experimental_files(repo, identifier):
    """Cheap read-only admission check, not CUDA/weight integrity certification."""
    names = {'thinktwice': 'ThinkTwice', 'driveadapter': 'DriveAdapter'}
    if identifier not in names:
        raise ValueError('Unknown original model')
    repo = Path(repo)
    root = repo / '.runtime/external-models' / names[identifier]
    paths = {
        'worker': repo / 'tools/run_opendrive_native.py',
        'adapter': repo / f'integration/opendrive/{identifier}_agent.py',
        'checkpoint': root / f'{identifier}-189k.pth',
        'config': root / f'open_loop_training/configs/{identifier}.py',
        'original_agent': root / f'leaderboard/team_code/{identifier}_agent.py',
        'planner': root / 'leaderboard/team_code/planner.py',
    }
    for label, path in paths.items():
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f'Missing or empty experimental {label}: {path}')
        try:
            with path.open('rb') as stream:
                if not stream.read(1):
                    raise RuntimeError(f'Empty experimental {label}: {path}')
        except OSError as error:
            raise RuntimeError(f'Unreadable experimental {label}: {path}') from error
    return {label: str(path) for label, path in paths.items()}

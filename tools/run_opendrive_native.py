"""Session-launched experimental OpenDriveLab worker, not a public preset."""
import os
from pathlib import Path
import sys


def main():
    repo = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo / 'src'))
    from carla_safety_agent.experimental_models import experimental_model_enabled
    algorithm = os.environ.get('ALGORITHM')
    if not experimental_model_enabled(algorithm):
        raise RuntimeError('Requested experimental model is not explicitly enabled')
    required = ('CSA_EXECUTION_ID', 'CSA_RESOURCE_DATA_ROOT', 'CSA_EVALUATION_CONTROL_DIR',
                'SCENARIO', 'CSA_SCENARIO_SHA256', 'RESULTS', 'BENCH2DRIVE_ROOT')
    if any(not os.environ.get(key) for key in required):
        raise RuntimeError('Launch through the reviewed scenario session, not directly')
    dependencies = repo / '.runtime/external-models'
    root = dependencies / {'thinktwice': 'ThinkTwice', 'driveadapter': 'DriveAdapter'}[algorithm]
    benchmark = Path(os.environ['BENCH2DRIVE_ROOT'])
    carla_root = Path(os.environ.get('CARLA_ROOT', '/home/moresweet/carla'))
    checkpoint = root / f'{algorithm}-189k.pth'
    config = root / f'open_loop_training/configs/{algorithm}.py'
    for path in (checkpoint, config):
        if not path.is_file():
            raise RuntimeError(f'Missing experimental dependency: {path}')
    sys.path[:0] = [str(dependencies/'cumm-compatible'), str(dependencies/'legacy-python'),
                   str(dependencies/'mmdetection3d-1.0'), str(carla_root/'PythonAPI/carla'),
                   str(benchmark/'leaderboard'), str(benchmark/'scenario_runner')]
    import torch
    import mmcv
    mmcv.__path__.append(str(dependencies/'mmcv-full-1.7.0/mmcv'))
    # Pin the host leaderboard package before exposing the original repository,
    # which bundles an incompatible older package of the same name.
    import leaderboard
    if Path(leaderboard.__file__).resolve() != (benchmark/'leaderboard/leaderboard/__init__.py').resolve():
        raise RuntimeError('Host leaderboard package was not selected')
    sys.path.insert(0, str(root/'leaderboard'))
    sys.path.extend([str(root), str(root/'open_loop_training')])
    # Bench2Drive also contains team_code/planner.py, but uses a different GPS
    # conversion. Mixing it with the original agent silently corrupts targets.
    from team_code import planner
    if Path(planner.__file__).resolve() != (root/'leaderboard/team_code/planner.py').resolve():
        raise RuntimeError('Original model route planner was not selected')
    from agents.navigation import global_route_planner
    if not Path(global_route_planner.__file__).resolve().is_relative_to((carla_root/'PythonAPI/carla').resolve()):
        raise RuntimeError('Native CARLA navigation package was shadowed by an external model')
    os.environ['E2E_EXECUTION_MODE'] = 'scenario'
    os.environ['ROUTES'] = os.environ['SCENARIO']
    os.environ['SAVE_PATH'] = str(Path(os.environ['CSA_EVALUATION_CONTROL_DIR']) /
                                  ('original-' + algorithm + '-' + os.environ['CSA_EXECUTION_ID']))
    os.environ['CSA_ALGORITHM_LABEL'] = algorithm + '-experimental'
    from carla_safety_agent.native_executor import main as execute
    sys.argv = [sys.argv[0], '--scenario', os.environ['SCENARIO'],
                '--agent', str(repo/f'integration/opendrive/{algorithm}_agent.py'),
                '--agent-config', str(checkpoint)+'+'+str(config),
                '--output', os.environ['RESULTS'], '--port', os.environ.get('CARLA_PORT', '2000')]
    return execute()


if __name__ == '__main__':
    raise SystemExit(main())

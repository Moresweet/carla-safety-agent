import json
import os
from pathlib import Path
import subprocess

import pytest

from carla_safety_agent.runtime_paths import diagnose_paths

ROOT = Path(__file__).resolve().parents[1]


def test_all_missing_is_not_runtime_success():
    result = diagnose_paths({})
    assert not result['paths_present']
    assert not result['runtime_verified']
    assert not result['code_executed']
    assert {r['state'] for r in result['checks']} == {'missing_configuration'}


def test_present_does_not_execute_or_certify_runtime(tmp_path):
    binary = tmp_path / 'not a real executable'
    binary.write_text('this must never be executed')
    binary.chmod(0o700)
    environment = {k: str(binary) for k in ('UE4_EDITOR', 'UE4_EDITOR_CMD', 'BLENDER_BIN',
                                            'UNIAD_PYTHON', 'CARLA_PROJECT')}
    environment.update(CARLA_PYTHONPATH=str(tmp_path), E2E_ROOT=str(tmp_path))
    result = diagnose_paths(environment)
    assert result['paths_present'] and not result['runtime_verified']
    binary.chmod(0o600)
    assert diagnose_paths(environment)['checks'][0]['state'] == 'not_executable'


@pytest.mark.parametrize('path', ['relative/file', '/tmp/bad\npath', '', None])
def test_invalid_path(path):
    assert not diagnose_paths({'UE4_EDITOR': path}, 'native')['paths_present']


def test_native_scope_and_unknown_scope():
    assert len(diagnose_paths({}, 'native')['checks']) == 3
    with pytest.raises(ValueError):
        diagnose_paths({}, 'launch')


def test_shared_paths_propagate_overrides_without_shell_evaluation(tmp_path):
    env = dict(os.environ, CARLA_ROOT=str(tmp_path / 'carla $(false)'),
               UE4_ROOT=str(tmp_path / 'ue with spaces'), E2E_ROOT=str(tmp_path / 'models'),
               BLENDER_BIN='/custom/blender')
    for key in ('CARLA_PROJECT', 'CARLA_PYTHONPATH', 'UE4_EDITOR', 'UE4_EDITOR_CMD', 'UNIAD_PYTHON'):
        env.pop(key, None)
    result = subprocess.run(['bash', '-c',
        'source scripts/studio_paths.sh; python3 -c "import json,os; print(json.dumps(dict(os.environ)))"'],
        cwd=ROOT, env=env, text=True, capture_output=True, check=True)
    actual = json.loads(result.stdout)
    assert actual['CARLA_PROJECT'] == env['CARLA_ROOT'] + '/Unreal/CarlaUE4/CarlaUE4.uproject'
    assert actual['UE4_EDITOR_CMD'] == env['UE4_ROOT'] + '/Engine/Binaries/Linux/UE4Editor-Cmd'
    assert actual['UNIAD_PYTHON'].startswith(env['E2E_ROOT'] + '/')
    assert actual['BLENDER_BIN'] == '/custom/blender'


def test_restart_missing_editor_fails_before_world_or_process_operations(tmp_path):
    result = subprocess.run(['bash', 'scripts/restart_carla_native.sh'], cwd=ROOT,
        env=dict(os.environ, UE4_EDITOR=str(tmp_path / 'missing-editor')), text=True,
        capture_output=True, timeout=10)
    assert result.returncode != 0
    report = json.loads(result.stdout)
    assert report['checks'][0]['state'] == 'missing'
    assert not report['world_modified']
    # The preflight precedes any RPC, PID read, or stop command in the script.
    script = (ROOT / 'scripts/restart_carla_native.sh').read_text()
    assert script.index('tools/runtime_paths_doctor.py') < script.index('scenes/save')
    assert script.index('tools/runtime_paths_doctor.py') < script.index('kill -TERM')

import pytest
from carla_safety_agent.experimental_models import experimental_model_enabled


@pytest.mark.parametrize('flag', [None, '', '0', 'true', '1'])
def test_opt_in_is_exact_and_only_for_one_development_model(monkeypatch, flag):
    monkeypatch.delenv('CSA_EXPERIMENTAL_DRIVEADAPTER', raising=False)
    monkeypatch.delenv('CSA_EXPERIMENTAL_THINKTWICE', raising=False)
    if flag is not None:
        monkeypatch.setenv('CSA_EXPERIMENTAL_THINKTWICE', flag)
    assert experimental_model_enabled('thinktwice') == (flag == '1')
    for other in ('driveadapter', 'vad', None, True):
        assert not experimental_model_enabled(other)


@pytest.mark.parametrize('flag', [None, '', '0', 'true', '1'])
def test_driveadapter_requires_its_own_explicit_flag(monkeypatch, flag):
    monkeypatch.delenv('CSA_EXPERIMENTAL_THINKTWICE', raising=False)
    monkeypatch.delenv('CSA_EXPERIMENTAL_DRIVEADAPTER', raising=False)
    if flag is not None:
        monkeypatch.setenv('CSA_EXPERIMENTAL_DRIVEADAPTER', flag)
    assert experimental_model_enabled('driveadapter') == (flag == '1')
    assert not experimental_model_enabled('thinktwice')
    for unknown in ('vad', None, True, [], {}):
        assert not experimental_model_enabled(unknown)
from pathlib import Path
import pytest


@pytest.mark.parametrize('model,directory', [('thinktwice','ThinkTwice'),('driveadapter','DriveAdapter')])
def test_required_original_files_fail_before_launch(tmp_path, model, directory):
    from carla_safety_agent.experimental_models import require_experimental_files
    root = tmp_path / '.runtime/external-models' / directory
    paths = [tmp_path/'tools/run_opendrive_native.py',
             tmp_path/f'integration/opendrive/{model}_agent.py',
             root/f'{model}-189k.pth', root/f'open_loop_training/configs/{model}.py',
             root/f'leaderboard/team_code/{model}_agent.py', root/'leaderboard/team_code/planner.py']
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'fixture')
    assert len(require_experimental_files(tmp_path, model)) == 6
    for path in paths:
        path.write_bytes(b'')
        with pytest.raises(RuntimeError, match='Missing or empty'):
            require_experimental_files(tmp_path, model)
        path.unlink()
        with pytest.raises(RuntimeError, match='Missing or empty'):
            require_experimental_files(tmp_path, model)
        path.write_bytes(b'fixture')
    with pytest.raises(ValueError):
        require_experimental_files(tmp_path, '../other')

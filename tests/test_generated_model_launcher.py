import os
import subprocess
from pathlib import Path
import pytest


@pytest.mark.parametrize('algorithm,agent,checkpoint', [
    ('uniad-tiny','team_code/uniad_b2d_agent.py','uniad_tiny_b2d.pth'),
    ('uniad-base','team_code/uniad_b2d_agent.py','uniad_base_b2d.pth'),
    ('vad','vad_agent.py','vad_b2d_base.pth'),
    ('tcp','tcp_agent.py','tcp_b2d.ckpt'),
    ('admlp','admlp_agent.py','admlp_b2d.ckpt'),
])
def test_generated_launcher_selects_existing_model_adapter(tmp_path, algorithm, agent, checkpoint):
    root = Path(__file__).resolve().parents[1]
    zoo = tmp_path/'zoo'; (zoo/'ckpts').mkdir(parents=True)
    (zoo/'team_code').mkdir()
    (zoo/'team_code/uniad_b2d_agent.py').touch()
    (zoo/'ckpts'/checkpoint).touch()
    env = {**os.environ, 'BENCH2DRIVE_ZOO': str(zoo), 'BENCH2DRIVE_TCP_ZOO': str(zoo),
           'E2E_EXECUTION_MODE': 'scenario', 'SCENARIO': str(tmp_path/'scenario.json'),
           'ALGORITHM': algorithm, 'E2E_CHECK_ONLY': '1', 'RESULTS': str(tmp_path/'result.json')}
    result = subprocess.run(['bash', str(root/'scripts/run_benchmark_preset.sh')],
                            env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert agent in result.stdout and checkpoint in result.stdout

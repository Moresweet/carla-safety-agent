import os
from pathlib import Path
import subprocess
import sys
import pytest


@pytest.mark.parametrize('arguments', [
    ['--models', 'vad', 'vad'],
    ['--model', 'tcp', '--models', 'admlp'],
    ['--models', 'not-installed'],
    ['--model', 'vad', '--cancel-resume'],
    ['--seeds', '31', '--cancel-resume'],
])
def test_invalid_model_matrix_rejected_before_network(arguments):
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, str(root/'tools/regression_batch_service.py'), *arguments],
                            env={**os.environ, 'PYTHONPATH': str(root/'src')},
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 2
    assert 'error:' in result.stderr and not result.stdout

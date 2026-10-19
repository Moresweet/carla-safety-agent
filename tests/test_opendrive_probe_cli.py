"""Probe argument guards must work without Torch, GPU or simulator access."""
from pathlib import Path
import subprocess
import sys

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / 'tools/probe_opendrive_environment.py'


@pytest.mark.parametrize('extra,message', [
    (['--voxel-pooling', '.'], 'requires an existing directory and --gpu-probe'),
    (['--thinktwice-root', '.'], 'requires --thinktwice-root and --checkpoint'),
    (['--checkpoint', 'weight.pth'], 'requires --thinktwice-root and --checkpoint'),
    (['--thinktwice-root', '.', '--checkpoint', 'weight.pth', '--sparse-only'],
     'requires --thinktwice-root and --checkpoint'),
    (['--driveadapter-root', '.'], 'requires --thinktwice-root and --checkpoint'),
    (['--thinktwice-root', '.', '--driveadapter-root', '.', '--checkpoint', 'weight.pth'], 'exactly one model root'),
    (['--driveadapter-root', '.', '--checkpoint', 'weight.pth', '--synthetic-forward'], 'requires a model and --gpu-probe'),
])
def test_invalid_probe_requests_fail_before_dependency_import(tmp_path, extra, message):
    result = subprocess.run([sys.executable, str(SCRIPT), '--packages', str(tmp_path),
                             '--mmdet3d', str(tmp_path), '--native-ops', str(tmp_path), *extra],
                            cwd=tmp_path, capture_output=True, text=True, timeout=10)
    assert result.returncode == 2
    assert message in result.stderr
    assert not result.stdout
    assert list(tmp_path.iterdir()) == []


def test_existing_evidence_is_never_overwritten(tmp_path):
    evidence = tmp_path / 'evidence.json'
    evidence.write_text('original evidence', encoding='utf-8')
    result = subprocess.run([sys.executable, str(SCRIPT), '--packages', str(tmp_path),
                             '--mmdet3d', str(tmp_path), '--native-ops', str(tmp_path),
                             '--report', str(evidence)],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 2
    assert '--report must be a new file' in result.stderr
    assert evidence.read_text(encoding='utf-8') == 'original evidence'

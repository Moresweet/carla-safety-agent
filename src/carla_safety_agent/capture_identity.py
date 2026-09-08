"""Verify dataset scenario ownership against a persisted execution record."""
import json
from pathlib import Path
from .scenario_archive import read_verified_scenario


def verify_capture_identity(dataset, execution):
    root = Path(dataset).resolve()
    manifest_path = root/'manifest.json'
    if manifest_path.is_symlink() or manifest_path.stat().st_size > 8*1024*1024:
        raise ValueError('Invalid capture manifest path or size')
    manifest = json.loads(manifest_path.read_text())
    if manifest.get('execution_id') != execution['run_id']:
        raise ValueError('Capture execution identity mismatch')
    reference = manifest.get('scenario')
    if not isinstance(reference, dict):
        raise ValueError('Capture has no archived scenario identity')
    name = reference.get('path')
    if not isinstance(name, str) or Path(name).name != name or name in ('', '.', '..'):
        raise ValueError('Invalid capture scenario path')
    expected = execution['configuration'].get('scenario_sha256')
    if not expected or reference.get('sha256') != expected:
        raise ValueError('Capture scenario differs from execution')
    scenario, digest = read_verified_scenario(root/name, expected)
    if reference.get('scenario_id') != scenario.get('scenario_id') or manifest.get('scenario_id') != scenario.get('scenario_id'):
        raise ValueError('Capture scenario ID mismatch')
    return {'execution_id': execution['run_id'], 'scenario_sha256': digest}

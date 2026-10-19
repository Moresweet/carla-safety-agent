"""Read-only dependency receipt; does not copy, install, download or load weights."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import re


def verify_receipt(root, receipt):
    root = Path(root).resolve()
    if receipt.get('schema') != 'original-model-dependency-receipt/1':
        raise ValueError('Unknown dependency receipt schema')
    if set(receipt.get('models', {})) != {'thinktwice', 'driveadapter'}:
        raise ValueError('Receipt must contain both original models')
    groups = [receipt['shared_adaptations'], *[row['files'] for row in receipt['models'].values()]]
    checked, failures, seen = 0, [], set()
    for group in groups:
        if not isinstance(group, dict) or not group:
            raise ValueError('Empty or invalid dependency file group')
        for name, expected in group.items():
            path = Path(name)
            if (path.is_absolute() or '..' in path.parts or str(path) != name
                    or '\\' in name or name in seen):
                raise ValueError('Invalid or duplicate dependency path')
            seen.add(name)
            target = root / path
            if not target.resolve().is_relative_to(root):
                raise ValueError('Dependency escapes project root')
            if (not isinstance(expected, dict) or set(expected) != {'bytes', 'sha256'}
                    or type(expected['bytes']) is not int or expected['bytes'] < 0
                    or not isinstance(expected['sha256'], str)
                    or not re.fullmatch('[0-9a-f]{64}', expected['sha256'])):
                raise ValueError('Invalid dependency fingerprint')
            try:
                actual = fingerprint(target)
                if actual != expected:
                    failures.append({'path': name, 'reason': 'fingerprint_mismatch'})
            except OSError as error:
                failures.append({'path': name, 'reason': type(error).__name__})
            checked += 1
    return {'ok': not failures, 'checked_files': checked, 'failures': failures,
            'scope': 'Listed file bytes only; no environment, source-tree or runtime restoration certification',
            'restoration_verified': False}


def fingerprint(path):
    digest = hashlib.sha256()
    size = 0
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
            size += len(block)
    return {'bytes': size, 'sha256': digest.hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--output', type=Path)
    mode.add_argument('--verify', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.verify:
        result = verify_receipt(root, json.loads(args.verify.read_text()))
        print(json.dumps(result))
        return 0 if result['ok'] else 1
    if args.output.exists() or args.output.is_symlink():
        parser.error('Output must be a new file')
    root = Path(__file__).resolve().parents[1]
    receipt = {'schema': 'original-model-dependency-receipt/1', 'models': {},
               'local_sha256_not_upstream_attestation': True,
               'scope': 'Inventory only; weights, compiled libraries, environment and uncommitted source are not bundled',
               'restoration_verified': False}
    for name, directory in (('thinktwice', 'ThinkTwice'), ('driveadapter', 'DriveAdapter')):
        source = root / '.runtime/external-models' / directory
        commit = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
        dirty = subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain', '--untracked-files=no'], text=True)
        files = [source / (name + '-189k.pth'), source / f'open_loop_training/configs/{name}.py',
                 source / f'leaderboard/team_code/{name}_agent.py',
                 source / 'leaderboard/team_code/planner.py',
                 source / 'leaderboard/leaderboard/autoagents/agent_wrapper.py',
                 root / f'integration/opendrive/{name}_agent.py']
        if name == 'driveadapter':
            files.append(source / 'open_loop_training/ev_mask.npy')
        receipt['models'][name] = {'source_commit': commit, 'tracked_source_dirty': bool(dirty),
            'files': {str(path.relative_to(root)): fingerprint(path) for path in files}}
    receipt['shared_adaptations'] = {name: fingerprint(root / name) for name in (
        'integration/uniad/opendrive-mmcv17-torch27.patch',
        'integration/uniad/opendrive-isolated-requirements.txt',
        'src/carla_safety_agent/legacy_sparse_weights.py',
        'src/carla_safety_agent/strict_model_weights.py',
        'src/carla_safety_agent/opendrive_sensor_profile.py',
        'tools/run_opendrive_native.py')}
    with args.output.open('x') as stream:
        json.dump(receipt, stream, indent=2)
    print(json.dumps({'receipt': str(args.output.resolve()), 'restoration_verified': False}))


if __name__ == '__main__':
    raise SystemExit(main())

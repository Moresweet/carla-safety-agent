"""Explicitly rescan an existing saved capture via the deployed local bridge."""
import argparse
import hashlib
import json
import time
from pathlib import Path

from regression_scene_versions import request, ROOT
from carla_safety_agent.replay import dataset_path
from carla_safety_agent.restart_guard import verify_dataset_jobs_idle
from carla_safety_agent.owned_resources import durable_write


def snapshot(root):
    result = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError('Linked capture file')
        if path.is_file():
            digest = hashlib.sha256()
            with path.open('rb') as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(chunk)
            result[str(path.relative_to(root))] = digest.hexdigest()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        raise ValueError('Receipt must be new')
    capture = dataset_path(ROOT / '.runtime/generated-scenarios', args.run_id)
    before = snapshot(capture)
    reports = ROOT / '.runtime/dataset-quality'
    report_path = reports / (hashlib.sha256(args.run_id.encode()).hexdigest() + '.json')
    old = json.loads(report_path.read_text()) if report_path.exists() else None
    history_before = set((reports / 'history').glob('*.json'))
    verify_dataset_jobs_idle(request('datasets/jobs'))
    started = request('datasets/quality', {'run_id': args.run_id})
    if started.get('state') != 'running':
        raise ValueError('Quality scan not admitted')
    deadline = time.monotonic() + 30
    while True:
        result = request('datasets/quality?run_id=' + args.run_id)
        if result.get('state') != 'running':
            break
        if time.monotonic() >= deadline:
            raise TimeoutError('Scan still running; inspect same job, do not resubmit')
        time.sleep(.2)
    assert result['state'] == 'passed', result
    assert result['manifest_freshness'] == 'unchanged', result
    assert result.get('problem_frame') is None
    assert 'problem_frame' in result, 'New validator report contract missing'
    assert snapshot(capture) == before, 'Capture files changed during scan'
    history = set((reports / 'history').glob('*.json')) - history_before
    if old is not None:
        assert any(json.loads(path.read_text()) == old for path in history), 'Previous report not archived'
    saved = json.loads(report_path.read_text())
    assert saved['started_at_unix'] == result['started_at_unix']
    verify_dataset_jobs_idle(request('datasets/jobs'))
    receipt = {'passed': True, 'run_id': args.run_id, 'result': result,
               'capture_sha256': before, 'history_added': [str(p) for p in sorted(history)],
               'scope': 'Deployed successful rescan, durable result, old report archive, unchanged capture; not failure injection or driving safety'}
    durable_write(args.output, receipt, exclusive=True)
    print(json.dumps({'passed': True, 'receipt': str(args.output), 'files_unchanged': len(before)}))


if __name__ == '__main__':
    main()

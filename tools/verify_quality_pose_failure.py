"""Run the real validator against a private, corrupted copy; preserve source."""
import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

from verify_deployed_quality import snapshot
from regression_scene_versions import ROOT
from carla_safety_agent.capture_quality import audit_capture
from carla_safety_agent.owned_resources import durable_write
from carla_safety_agent.replay import dataset_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        raise ValueError('Receipt must be new')
    source = dataset_path(ROOT/'.runtime/generated-scenarios', args.run_id)
    before = snapshot(source)
    validator = ROOT/'tools/validate_capture_dataset.py'
    with tempfile.TemporaryDirectory(prefix='carla-quality-pose-') as temporary:
        copied = Path(temporary)/source.name
        shutil.copytree(source, copied)
        baseline = audit_capture(copied, validator, sys.executable)
        assert baseline['state'] == 'passed', baseline
        frame = json.loads((copied/'index.json').read_text())['frames'][0]['frame']
        path = copied/'samples'/f'{frame:010d}'/'frame.json'
        original = path.read_bytes()
        row = json.loads(original)
        row['ego']['matrix'][0][:3] = [0, 0, 0]
        durable_write(path, row)
        failure = audit_capture(copied, validator, sys.executable)
        assert failure['state'] == 'failed', failure
        assert failure['reason_code'] == 'invalid_ego_pose', failure
        assert failure['problem_frame'] == frame, failure
        durable_write(path, json.loads(original))
        restored = audit_capture(copied, validator, sys.executable)
        assert restored['state'] == 'passed', restored
    assert snapshot(source) == before, 'Original recording changed'
    durable_write(args.output, {'passed': True, 'source_run_id': args.run_id,
        'source_sha256': before, 'baseline': baseline, 'injected_failure': failure,
        'restored': restored, 'temporary_copy_removed': True,
        'scope': 'Real validator subprocess protocol on private copy; not deployed HTTP failure or browser acceptance'}, exclusive=True)
    print(json.dumps({'passed': True, 'problem_frame': frame, 'source_files_unchanged': len(before),
                      'receipt': str(args.output)}))


if __name__ == '__main__':
    main()

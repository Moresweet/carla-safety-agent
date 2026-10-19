"""Archive/restore real inactive sensor data in temporary storage, preserving source."""
import argparse
import json
import sys
import tempfile
from pathlib import Path

from carla_safety_agent.capture_archive import archive_capture, restore_capture_archive
from carla_safety_agent.capture_quality import audit_capture
from carla_safety_agent.capture_recovery import inventory, require_inactive_execution
from carla_safety_agent.owned_resources import durable_write
from carla_safety_agent.scene_store import identifier, read_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.output.exists() or args.output.is_symlink():
        raise ValueError('Receipt must be new')
    source = root/'.runtime/generated-scenarios'/identifier(args.run_id)
    manifest = read_json(source/'manifest.json', max_bytes=8*1024**2)
    execution = identifier(manifest.get('execution_id'))
    guard = lambda: require_inactive_execution(root/'data', execution)
    guard()
    before, size = inventory(source)
    with tempfile.TemporaryDirectory(prefix='carla-archive-roundtrip-') as temporary:
        archive = archive_capture(source, Path(temporary)/'capture.zip', guard)
        restored = restore_capture_archive(archive['archive'], temporary)
        assert inventory(Path(restored['directory'])) == (before, size)
        quality = audit_capture(Path(restored['directory']), root/'tools/validate_capture_dataset.py', sys.executable)
        assert quality['state'] == 'passed', quality
        archive_size = archive['archive_bytes']
    guard()
    assert inventory(source) == (before, size), 'Source changed during roundtrip'
    result = {'passed': True, 'source_run_id': args.run_id, 'source_bytes': size,
              'source_files': before, 'archive_bytes': archive_size, 'quality': quality,
              'source_unchanged': True, 'temporary_copies_removed': True,
              'scope': 'Real archive/isolated restore and raw sensor validation; not cross-machine or low-disk stress'}
    durable_write(args.output, result, exclusive=True)
    print(json.dumps({k:v for k,v in result.items() if k not in ('source_files', 'quality')}))


if __name__ == '__main__':
    main()

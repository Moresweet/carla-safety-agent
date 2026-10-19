"""Remove one reviewed one-second intermediate capture, retaining audit metadata."""
import argparse
import json
import shutil
import uuid

from cleanup_superseded_model_captures import ROOT, idle
from carla_safety_agent.capture_quota import capture_write_lock
from carla_safety_agent.capture_recovery import inventory, require_inactive_execution
from carla_safety_agent.capture_retention import CaptureRetention
from carla_safety_agent.capture_references import capture_references, queue_references, project_references
from carla_safety_agent.split_registry import registry_mutation_lock, require_no_registered_split_references

TARGET = 'capture-20260914T122421-791fd035'
EXECUTION = '7150deeb5c964e0faa06b48e70a2aebf'
KEEP = 'capture-20260908T161417-253a8410'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    root, data = ROOT / '.runtime/generated-scenarios', ROOT / 'data'
    source = root / TARGET
    if root.is_symlink() or source.is_symlink():
        raise ValueError('Linked root or target')
    idle()
    with capture_write_lock(root), registry_mutation_lock(data / 'dataset-splits'):
        markers = CaptureRetention(data, root).snapshot()

        def guard():
            idle()
            assert CaptureRetention(data, root).snapshot() == markers
            assert TARGET not in markers['records'] and KEEP in markers['records']
            kept = json.loads((root / KEEP / 'manifest.json').read_text())
            assert kept['status'] == 'saved' and kept['frame_count'] == 400
            refs = capture_references(root)
            projects = project_references(data / 'project-bundles')
            queues = queue_references(data / 'experiment-queues')
            assert refs['complete'] and projects['reference_scan_complete'] and queues['complete']
            assert not refs['references'].get(TARGET) and not projects['references'].get(TARGET)
            assert not queues['references'].get(EXECUTION)
            require_no_registered_split_references(data / 'dataset-splits', [TARGET])
            require_inactive_execution(data, EXECUTION)
            manifest = json.loads((source / 'manifest.json').read_text())
            assert manifest['run_id'] == TARGET and manifest['execution_id'] == EXECUTION
            assert manifest['status'] == 'saved' and manifest['frame_count'] == 20 and manifest['model'] is None

        guard()
        files, size = inventory(source)
        result = {'target': TARGET, 'logical_bytes': size, 'retained_baseline': KEEP,
                  'reason': 'Unreferenced one-second intermediate capture; retain longer rule capture baseline and all execution/results logs. Not a byte-identical replacement.',
                  'raw_recoverable': False, 'deleted': False}
        if args.execute:
            out = ROOT / 'runs/validation' / ('short-capture-cleanup-' + uuid.uuid4().hex)
            out.mkdir()
            for relative in files:
                if relative.endswith('.json'):
                    destination = out / 'metadata' / TARGET / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source / relative, destination)
            (out / 'plan.json').write_text(json.dumps({'decision': result, 'files': files}, indent=2))
            guard()
            assert inventory(source)[0] == files
            shutil.rmtree(source)
            result.update(deleted=True, receipt=str(out))
            (out / 'result.json').write_text(json.dumps(result, indent=2))
        print(json.dumps(result))


if __name__ == '__main__':
    main()

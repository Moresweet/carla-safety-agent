"""Remove only two byte-verified redundant recovery copies; retain metadata."""
import argparse
import json
import shutil
import uuid
from cleanup_superseded_model_captures import ROOT, idle
from carla_safety_agent.capture_recovery import inventory, require_inactive_execution
from carla_safety_agent.capture_retention import CaptureRetention
from carla_safety_agent.capture_references import capture_references, queue_references, project_references
from carla_safety_agent.split_registry import registry_mutation_lock, require_no_registered_split_references
from carla_safety_agent.capture_quota import capture_write_lock

TARGETS = ('recovered-e0f80435373d4fdba83aac8d8d06bcb2', 'recovered-d591b839253244fa8f0c830491dfbb4c')
KEEP = 'recovered-4f6835a9ab294e358ef6ad40d0d1c1d3'
SOURCE = 'capture-20260910T165555-a6a12724'

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    root = ROOT / '.runtime/generated-scenarios'
    data = ROOT / 'data'
    if root.is_symlink():
        raise ValueError('Linked root')
    idle()
    with capture_write_lock(root), registry_mutation_lock(data / 'dataset-splits'):
        markers = CaptureRetention(data, root).snapshot()
        refs = capture_references(root)
        projects = project_references(data / 'project-bundles')
        queues = queue_references(data / 'experiment-queues')
        assert refs['complete'] and projects['reference_scan_complete'] and queues['complete']
        require_no_registered_split_references(data / 'dataset-splits', TARGETS)
        assert (root / SOURCE / 'manifest.json').is_file()
        kept, _ = inventory(root / KEEP)
        rows = []
        for name in TARGETS:
            assert name not in markers['records']
            assert not refs['references'].get(name) and not projects['references'].get(name)
            files, size = inventory(root / name)
            manifest = json.loads((root / name / 'manifest.json').read_text())
            replacement = json.loads((root / KEEP / 'manifest.json').read_text())
            for m in (manifest, replacement):
                assert m['status'] == 'saved_recovered' and m['frame_count'] == 5
                assert m['recovery']['source_run_id'] == SOURCE
                require_inactive_execution(data, m['execution_id'])
                assert not queues['references'].get(m['execution_id'])
            # Run identity and historical audit timestamps differ; archive both.
            # Every sample, calibration, scenario and index must match exactly.
            metadata = {'manifest.json', 'recovery.json'}
            assert {k:v for k,v in files.items() if k not in metadata} == {k:v for k,v in kept.items() if k not in metadata}
            reports = [json.loads((root / n / 'recovery.json').read_text()) for n in (name, KEEP)]
            assert reports[0]['source_files'] == reports[1]['source_files']
            assert reports[0]['omitted_uncommitted_tail'] == reports[1]['omitted_uncommitted_tail']
            for report in reports:
                assert report['source_run_id'] == SOURCE
                assert report['source_unchanged'] is True and report['raw_data_verified'] is True
                assert report['audit']['state'] == 'passed'
            rows.append({'source': name, 'replacement': KEEP, 'logical_bytes': size, 'files': files})
        if not args.execute:
            print(json.dumps({'reviewed': rows, 'deleted': []}))
            return
        out = ROOT / 'runs/validation' / ('duplicate-recovery-cleanup-' + uuid.uuid4().hex)
        out.mkdir()
        for row in rows:
            for relative in row['files']:
                if relative.endswith('.json'):
                    target = out / 'metadata' / row['source'] / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(root / row['source'] / relative, target)
        (out / 'plan.json').write_text(json.dumps(rows, indent=2))
        for row in rows:
            idle()
            assert CaptureRetention(data, root).snapshot() == markers
            assert inventory(root / KEEP)[0] == kept
            assert inventory(root / row['source'])[0] == row['files']
            shutil.rmtree(root / row['source'])
            with (out / 'deleted.jsonl').open('a') as stream:
                stream.write(json.dumps({'deleted': row['source'], 'replacement': KEEP}) + '\n')
        result = {'deleted': list(TARGETS), 'replacement': KEEP, 'removed_logical_bytes': sum(r['logical_bytes'] for r in rows), 'metadata_receipt': str(out), 'raw_samples_retained_in_replacement': True}
        (out / 'result.json').write_text(json.dumps(result, indent=2))
        print(json.dumps(result))

if __name__ == '__main__':
    main()

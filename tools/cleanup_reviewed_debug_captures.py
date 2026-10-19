"""One-off reviewed intermediate crash-debug recordings; explicit execution only."""
import argparse
import json
import shutil
import uuid

from cleanup_superseded_model_captures import ROOT, idle
from carla_safety_agent.capture_recovery import inventory, require_inactive_execution
from carla_safety_agent.capture_references import capture_references, queue_references, project_references
from carla_safety_agent.capture_retention import CaptureRetention
from carla_safety_agent.split_registry import registry_mutation_lock, require_no_registered_split_references

TARGETS = (
    'capture-20260908T142028-4e6ac169',
    'capture-20260908T142506-11236003',
    'capture-20260908T142759-b8ac6474',
    'capture-20260908T143043-0efa0252',
    'capture-20260908T143403-25f884b1',
    'capture-20260908T143814-6f40de75',
)
KEEP = ('capture-20260908T140307-84bc487e', 'capture-20260908T141120-3da1e8ac',
        'capture-20260908T144240-2449a583', 'capture-20260908T144342-4f903e7e')


def main():
    global TARGETS, KEEP
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true', required=True)
    parser.add_argument('--interrupted-thinktwice', action='store_true',
                        help='Only reviewed interrupted observer run; preserve cancellation and full baselines')
    args = parser.parse_args()
    expected_frames, expected_model = 60, None
    reason = 'Intermediate native crash diagnostics; retain first failure and repaired baselines.'
    if args.interrupted_thinktwice:
        TARGETS = ('capture-20260915T181936-f8564bbc',)
        KEEP = ('capture-20260915T181234-755a59be', 'capture-20260915T183736-10c0f89d',
                'capture-20260915T183237-1037985b')
        expected_frames, expected_model = 56, 'thinktwice-experimental'
        reason = ('Observer interrupted with 143; model subsequently stopped normally. '
                  'Not successful fault-injection evidence. Preserve all JSON, hashes and execution logs; '
                  'retain cancellation fixture and Town04/Town05 full baselines.')
    root = ROOT / '.runtime/generated-scenarios'
    if root.is_symlink():
        raise ValueError('Linked root')
    data = ROOT / 'data'
    markers = CaptureRetention(data, root).snapshot()

    def guard():
        idle()
        if CaptureRetention(data, root).snapshot() != markers:
            raise ValueError('Retention changed')
        if not all((root / name / 'manifest.json').is_file() for name in KEEP):
            raise ValueError('Required failure/repair evidence missing')
        derived = capture_references(root)
        queues = queue_references(data / 'experiment-queues')
        projects = project_references(data / 'project-bundles')
        if not derived['complete'] or not queues['complete'] or not projects['reference_scan_complete']:
            raise ValueError('Reference scan incomplete')
        require_no_registered_split_references(data / 'dataset-splits', TARGETS)
        for name in TARGETS:
            if name in markers['records'] or derived['references'].get(name) or projects['references'].get(name):
                raise ValueError('Protected recording: ' + name)
            path = root / name
            if not path.exists():
                continue
            if path.is_symlink() or (path / 'manifest.json').is_symlink():
                raise ValueError('Linked recording')
            manifest = json.loads((path / 'manifest.json').read_text())
            if manifest['run_id'] != name or manifest['status'] != 'saved' or manifest['frame_count'] != expected_frames or manifest['model'] != expected_model:
                raise ValueError('Reviewed identity changed')
            execution = manifest['execution_id']
            if queues['references'].get(execution):
                raise ValueError('Queue reference')
            require_inactive_execution(data, execution)

    guard()
    out = ROOT / 'runs/validation' / ('debug-cleanup-' + uuid.uuid4().hex)
    out.mkdir()
    rows = []
    for name in TARGETS:
        source = root / name
        evidence, size = inventory(source)
        saved = out / 'metadata' / name
        for relative in evidence:
            if relative.endswith('.json'):
                target = saved / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source / relative, target)
        rows.append({'source': name, 'logical_bytes': size, 'files': evidence})
    (out / 'plan.json').write_text(json.dumps({'rows': rows, 'preserved': KEEP,
        'reason': reason,
        'raw_recoverable': False}, indent=2))
    for row in rows:
        with registry_mutation_lock(data / 'dataset-splits'):
            guard()
            source = root / row['source']
            if inventory(source)[0] != row['files']:
                raise ValueError('Recording changed')
            shutil.rmtree(source)
            with (out / 'deleted.jsonl').open('a') as stream:
                stream.write(json.dumps({'source': row['source'], 'raw_recoverable': False}) + '\n')
    result = {'deleted': list(TARGETS), 'preserved': list(KEEP),
              'removed_logical_bytes': sum(row['logical_bytes'] for row in rows),
              'raw_recoverable': False, 'receipt': str(out)}
    (out / 'result.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


if __name__ == '__main__':
    main()

"""Measure recording storage without deleting, modifying or opening raw arrays."""
import argparse
import json
from pathlib import Path
from carla_safety_agent.capture_storage import inventory_captures
from carla_safety_agent.capture_retention import CaptureRetention
from carla_safety_agent.capture_references import capture_references, split_references, queue_references, project_references
from carla_safety_agent.split_registry import registered_split_references


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1]/'.runtime/generated-scenarios')
    parser.add_argument('--output', type=Path, required=True, help='New receipt file; existing files are never overwritten')
    parser.add_argument('--data-root', type=Path, default=Path(__file__).resolve().parents[1]/'data')
    parser.add_argument('--split', type=Path, action='append', default=[], help='Explicit saved split to include in reference checks; repeatable')
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error('Output already exists')
    protection = CaptureRetention(args.data_root, args.root).snapshot()
    result = inventory_captures(args.root)
    references = capture_references(args.root)
    result['derived_references'] = references
    result['complete'] = result['complete'] and references['complete']
    result['warnings'].extend(references['warnings'])
    splits = split_references(args.split)
    registered = registered_split_references(args.data_root/'dataset-splits')
    result['registered_split_references'] = registered
    for run, registered_refs in registered['references'].items():
        splits['references'].setdefault(run, []).extend(registered_refs)
    splits['warnings'].extend(registered['warnings'])
    splits['complete'] = splits['complete'] and registered['complete']
    splits['scanned_files'] += registered['scanned_files']
    splits['scope'] = 'Registered local splits plus explicitly supplied files; other external splits not scanned; not deletion approval'
    result['split_references'] = splits
    result['complete'] = result['complete'] and splits['complete']
    result['warnings'].extend(splits['warnings'])
    queues = queue_references(args.data_root/'experiment-queues')
    result['queue_references'] = queues
    result['complete'] = result['complete'] and queues['complete']
    result['warnings'].extend(queues['warnings'])
    projects = project_references(args.data_root/'project-bundles')
    result['project_references'] = projects
    result['complete'] = result['complete'] and projects['complete']
    result['warnings'].extend(projects['warnings'])
    # Packaging warnings and unreadable references are different conditions.
    # Neither a successful scan nor an empty reference list authorizes deletion.
    result['local_reference_scan_complete'] = all((references['complete'], splits['complete'],
        queues['complete'], projects['reference_scan_complete']))
    result['project_reference_scan_errors'] = projects['scan_errors']
    result['deletion_approved'] = False
    result['retention_revision'] = protection['revision']
    for row in result['recordings']:
        marker = protection['records'].get(row['directory'])
        row['explicit_keep'] = marker is not None
        row['keep_reason'] = marker['reason'] if marker else None
        row['derived_referenced_by'] = references['references'].get(row['directory'], [])
        row['split_referenced_by'] = splits['references'].get(row['directory'], [])
        row['project_referenced_by'] = projects['references'].get(row['directory'], [])
        execution = row.get('execution_id')
        row['queue_referenced_by'] = queues['references'].get(execution, []) if isinstance(execution, str) else []
    result['limitations'].append('Unmarked or unreferenced does not mean deletable; registered and explicitly supplied splits plus local validated project JSON scanned; other external references not scanned; queue matching requires manifest execution_id')
    with args.output.open('x') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps({'receipt': str(args.output.resolve()), 'complete': result['complete'],
        'local_reference_scan_complete': result['local_reference_scan_complete'],
        'project_reference_scan_errors': result['project_reference_scan_errors'],
        'deletion_approved': False,
        'recordings': len(result['recordings']), 'allocated_GiB': result['allocated_bytes']/1024**3,
        'warnings': result['warnings']}))


if __name__ == '__main__':
    main()

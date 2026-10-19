"""Validate saved project archives without extracting or deleting any content."""
import argparse
import json
import hashlib
import re
from pathlib import Path
from carla_safety_agent.project_bundle import read_bundle, inspect_legacy_asset_flags


def audit_partial(path):
    """Validate a staging snapshot and compare every payload with its final ZIP."""
    path = Path(path)
    if path.is_symlink() or not path.is_file() or not re.fullmatch('[a-f0-9]{32}\\.partial', path.name):
        raise ValueError('Not a recognized partial project archive')
    final = path.with_suffix('.zip')
    if final.is_symlink() or not final.is_file():
        raise ValueError('Finalized sibling missing or linked')
    _, staged = read_bundle(path)
    _, finished = read_bundle(final)
    matches = [name for name, payload in staged.items() if finished.get(name) == payload]
    return {'final_bundle': final.name, 'staged_entries': len(staged),
            'identical_entries': sorted(matches),
            'different_or_missing_entries': sorted(set(staged)-set(matches)),
            'all_payloads_duplicated': bool(staged) and len(matches) == len(staged),
            'scope': 'Validated staging payload comparison only; not deletion approval or active-task check'}


def audit_sources(path):
    """Compare staging sources with their exact finalized sibling, read-only."""
    path = Path(path)
    if path.is_symlink() or not path.is_dir() or not re.fullmatch('[a-f0-9]{32}-sources', path.name):
        raise ValueError('Not a recognized source staging directory')
    final = path.with_name(path.name.removesuffix('-sources')+'.zip')
    if final.is_symlink() or not final.is_file():
        raise ValueError('Finalized sibling missing or linked')
    _, files = read_bundle(final)
    entries = []
    for source in sorted(path.iterdir()):
        if source.is_symlink() or not source.is_file() or source.stat().st_size > 256*1024**2:
            raise ValueError('Unsafe or oversized source entry')
        payload = source.read_bytes()
        entries.append({'name':source.name, 'bytes':len(payload),
            'sha256':hashlib.sha256(payload).hexdigest(),
            'identical_final_entries':[name for name, content in files.items() if content == payload]})
    return {'final_bundle':final.name, 'entries':entries,
        'all_bytes_duplicated':bool(entries) and all(entry['identical_final_entries'] for entry in entries),
        'scope':'Byte duplication in a validated sibling only; not deletion approval or active-task check'}


def audit(root):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('Project bundle root must be a real directory')
    rows = []
    for path in sorted(root.iterdir()):
        row = {'name':path.name, 'validated':False}
        try:
            if path.is_symlink() or not path.is_file() or path.suffix != '.zip':
                raise ValueError('Not a regular finalized zip; left untouched')
            manifest, files = read_bundle(path)
            row.update(validated=True, schema_version=manifest['schema_version'],
                       dependencies=manifest['dependencies'], entries=len(files),
                       bytes=path.stat().st_size)
        except Exception as error:
            row['error'] = f'{type(error).__name__}: {error}'
            if path.name.endswith('-sources'):
                try: row['source_comparison'] = audit_sources(path)
                except Exception as comparison_error:
                    row['source_comparison_error'] = f'{type(comparison_error).__name__}: {comparison_error}'
            elif path.suffix == '.partial':
                try: row['partial_comparison'] = audit_partial(path)
                except Exception as comparison_error:
                    row['partial_comparison_error'] = f'{type(comparison_error).__name__}: {comparison_error}'
            elif path.suffix == '.zip' and str(error) == 'Dependency manifest mismatch':
                try:
                    before, files, current = inspect_legacy_asset_flags(path)
                    row['legacy_diagnosis'] = {
                        'migration': 'legacy-generated-asset-flags/1',
                        'payload_entries_verified': len(files),
                        'dependencies_before': before['dependencies'],
                        'dependencies_after': current,
                        'scope': 'Read-only exact legacy diagnosis; original archive remains invalid and unchanged'}
                except Exception as diagnosis_error:
                    row['legacy_diagnosis_error'] = f'{type(diagnosis_error).__name__}: {diagnosis_error}'
        rows.append(row)
    return {'schema_version':'project-storage-audit/1', 'root':str(root.absolute()),
            'archives':rows, 'complete':all(row['validated'] for row in rows),
            'scope':'Existing project bundle format validation only; no extraction or deletion; '
                    'does not scan arbitrary external references or certify absence of user annotations'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1]/'data/project-bundles')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink(): parser.error('Output already exists')
    result = audit(args.root)
    with args.output.open('x') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps({'receipt':str(args.output), 'complete':result['complete'],
                      'validated':sum(row['validated'] for row in result['archives']),
                      'unvalidated':[row for row in result['archives'] if not row['validated']]}))


if __name__ == '__main__':
    main()

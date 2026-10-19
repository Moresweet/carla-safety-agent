"""Conservative references from derived dataset manifests, not deletion approval."""
from pathlib import Path
import json
import io
import re
import zipfile
from .scene_store import identifier, read_json


def _source_documents(path, *, max_entries=256):
    """Yield bounded, read-only staging metadata; never follow links."""
    from .blender_package import read_asset, LIMIT
    total = 0
    for count, source in enumerate(sorted(path.iterdir())):
        if count >= max_entries:
            raise ValueError('Source staging scan limit reached')
        if source.is_symlink() or not source.is_file():
            raise ValueError('Unsafe source staging entry')
        total += source.stat().st_size
        if total > LIMIT:
            raise ValueError('Source staging exceeds size limit')
        if source.name == 'reference.json':
            yield source.name, read_json(source, max_bytes=1024*1024)
        elif re.fullmatch('[0-9]+[.]zip', source.name):
            manifest, _ = read_asset(source)
            yield source.name+'!manifest.json', manifest
        else:
            raise ValueError('Unrecognized source staging entry')


def project_references(root, *, max_bundles=500):
    """Conservative textual references in validated, locally saved project ZIPs.

    This deliberately retains incidental mentions too. It does not infer that
    absent mentions prove a recording can be deleted.
    """
    from .project_bundle import read_bundle, inspect_legacy_asset_flags
    root = Path(root)
    if type(max_bundles) is not int or max_bundles < 1:
        raise ValueError('max_bundles must be positive')
    references, warnings, scan_errors = {}, [], []
    count = 0
    if root.is_symlink() or not root.is_dir():
        return {'references':{}, 'complete':False, 'reference_scan_complete':False,
                'scan_errors':['Project bundle root missing or unsafe'],
                'warnings':['Project bundle root missing or unsafe'], 'scanned_bundles':0}
    pattern = re.compile(r'(?<![A-Za-z0-9_-])(?:capture-[A-Za-z0-9-]+|(?:recovered|excerpt)-[a-f0-9]{32})(?![A-Za-z0-9_-])')
    for path in sorted(root.iterdir()):
        if count >= max_bundles:
            warnings.append('Project bundle scan limit reached')
            scan_errors.append('Project bundle scan limit reached')
            break
        count += 1
        try:
            sources = bool(re.fullmatch('[a-f0-9]{32}-sources', path.name))
            if sources and not path.is_symlink() and path.is_dir():
                warnings.append(f'{path.name}: Unfinalized source staging; readable metadata references retained')
                documents = _source_documents(path)
                files = {}
            else:
                documents = []
                files = None
            staging = bool(re.fullmatch('[a-f0-9]{32}\\.partial', path.name))
            if files is None and (path.is_symlink() or not path.is_file() or (path.suffix != '.zip' and not staging)):
                raise ValueError('Not a regular finalized project ZIP')
            if staging:
                warnings.append(f'{path.name}: Unfinalized project snapshot; verified references retained if readable')
            try:
                if files is None:
                    _, files = read_bundle(path)
            except ValueError as error:
                if str(error) != 'Dependency manifest mismatch':
                    raise
                # Only the exact known legacy mismatch is allowed to expose
                # verified payloads. Keep the warning: this is not approval to
                # import the archive or delete any recording.
                _, files, _ = inspect_legacy_asset_flags(path)
                warnings.append(f'{path.name}: Legacy asset flags require migration; verified payload references retained')
            for name, payload in files.items():
                if name.endswith('.json'):
                    documents.append((name, json.loads(payload)))
                elif name.startswith('generated-assets/') and name.endswith('.zip'):
                    from .blender_package import read_asset
                    manifest, _ = read_asset(io.BytesIO(payload))
                    documents.append((name+'!manifest.json', manifest))
            for name, document in documents:
                # Parse JSON before walking its string values and keys. Do not
                # search compressed binary assets or deserialize arbitrary data.
                pending = [document]
                found = set()
                while pending:
                    value = pending.pop()
                    if isinstance(value, dict):
                        pending.extend(value.keys()); pending.extend(value.values())
                    elif isinstance(value, list): pending.extend(value)
                    elif isinstance(value, str): found.update(pattern.findall(value))
                for run in sorted(found):
                    references.setdefault(run, []).append({'kind':'project_text_reference',
                        'bundle':path.name, 'entry':name})
        except (ValueError, OSError, RecursionError, zipfile.BadZipFile, KeyError, TypeError, RuntimeError) as error:
            warnings.append(f'{path.name}: {error}')
            scan_errors.append(f'{path.name}: {error}')
    return {'references':references, 'complete':not warnings, 'warnings':warnings,
            'reference_scan_complete':not scan_errors, 'scan_errors':scan_errors,
            'scanned_bundles':count,
            'scope':'Textual capture IDs in validated local project JSON, recognized partial snapshots and verified exact legacy payloads; staging and legacy warnings remain incomplete; not external references or deletion approval'}


def queue_references(root, *, max_queues=5000):
    """Index all attempts, including failed/retried ones, by execution identity."""
    root = Path(root)
    if type(max_queues) is not int or max_queues < 1:
        raise ValueError('max_queues must be positive')
    references, warnings = {}, []
    count = 0
    if root.is_symlink() or not root.is_dir():
        return {'references':{}, 'complete':False, 'warnings':['Queue root missing or unsafe'], 'scanned_queues':0}
    for folder in sorted(root.iterdir()):
        if folder.is_symlink():
            warnings.append(f'Skipped linked queue entry: {folder.name}')
            continue
        if not folder.is_dir(): continue
        if count >= max_queues:
            warnings.append('Queue scan limit reached')
            break
        count += 1
        try:
            doc = read_json(folder/'queue.json', max_bytes=8*1024**2)
            if not isinstance(doc, dict) or doc.get('schema_version') != 'carla-experiment-queue/1':
                raise ValueError('Unsupported queue schema')
            jobs = doc.get('jobs')
            if not isinstance(jobs, list): raise ValueError('Invalid queue jobs')
            for job in jobs:
                if not isinstance(job, dict): raise ValueError('Invalid queue job')
                job_id = identifier(job.get('job_id'))
                attempts = job.get('attempts')
                if not isinstance(attempts, list): raise ValueError('Invalid queue attempts')
                for attempt in attempts:
                    if not isinstance(attempt, dict): raise ValueError('Invalid queue attempt')
                    attempt_id = identifier(attempt.get('attempt_id'))
                    if 'execution_id' not in attempt: raise ValueError('Missing execution identity')
                    execution = attempt['execution_id']
                    if execution is None: continue  # Reserved, not yet bound.
                    execution = identifier(execution)
                    references.setdefault(execution, []).append({'queue_id':folder.name,
                        'job_id':job_id, 'attempt_id':attempt_id, 'kind':'queue_attempt'})
        except (ValueError, OSError) as error:
            warnings.append(f'{folder.name}: {error}')
    return {'references':references, 'complete':not warnings, 'warnings':warnings,
            'scanned_queues':count,
            'scope':'Queue attempt execution IDs only; not report validation or atomic snapshot'}


def split_references(paths):
    """Read explicitly selected split files; never infer deletion eligibility."""
    references, warnings = {}, []
    scanned = 0
    for path in paths:
        path = Path(path)
        scanned += 1
        try:
            doc = read_json(path, max_bytes=8*1024**2)
            if not isinstance(doc, dict) or doc.get('schema_version') != 'carla-safety-split/0.1':
                raise ValueError('Unsupported split schema')
            assignments = doc.get('assignments')
            if not isinstance(assignments, dict) or set(assignments) != {'train', 'validation', 'test'}:
                raise ValueError('Invalid split assignments')
            seen = set()
            for partition, runs in assignments.items():
                if not isinstance(runs, list):
                    raise ValueError('Split partition must be a list')
                for run in runs:
                    run = identifier(run)
                    if run in seen:
                        raise ValueError('Duplicate split recording')
                    seen.add(run)
                    references.setdefault(run, []).append({
                        'path':str(path.absolute()), 'kind':'split', 'partition':partition})
            if 'datasets' in doc:
                evidence = doc['datasets']
                if not isinstance(evidence, dict):
                    raise ValueError('Invalid split evidence')
                # Preserve extra evidence references even on an inconsistent file.
                for run in evidence:
                    run = identifier(run)
                    if run not in seen:
                        references.setdefault(run, []).append({
                            'path':str(path.absolute()), 'kind':'split_evidence'})
                if set(evidence) != seen:
                    raise ValueError('Split evidence/assignment mismatch')
        except (ValueError, OSError) as error:
            warnings.append(f'{path}: {error}')
    return {'references':references, 'complete':not warnings, 'warnings':warnings,
            'scanned_files':scanned, 'scope':'Only explicitly supplied split files; not automatic discovery or data validation'}


def capture_references(root, *, max_manifests=5000):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('Capture root must be a real directory')
    if type(max_manifests) is not int or max_manifests < 1:
        raise ValueError('max_manifests must be positive')
    references, warnings, known = {}, [], set()
    count = 0
    for folder in sorted(root.iterdir()):
        if folder.is_symlink():
            warnings.append(f'Skipped linked entry: {folder.name}')
            continue
        if not folder.is_dir(): continue
        path = folder/'manifest.json'
        if not path.exists() and not path.is_symlink(): continue
        if count >= max_manifests:
            warnings.append('Manifest scan limit reached')
            break
        count += 1
        try:
            doc = read_json(path, max_bytes=8*1024**2)
            if not isinstance(doc, dict): raise ValueError('Manifest is not an object')
            # Older non-capture result manifests may not have a run_id. They
            # cannot silently supply a derived capture reference, however.
            if doc.get('run_id') is not None and doc['run_id'] != folder.name:
                raise ValueError('Manifest/directory identity mismatch')
            known.add(folder.name)
            for kind in ('recovery', 'excerpt'):
                if kind not in doc: continue
                value = doc[kind]
                if not isinstance(value, dict): raise ValueError(f'Invalid {kind} reference')
                source = identifier(value.get('source_run_id'))
                if source == folder.name: raise ValueError('Self-referencing dataset')
                references.setdefault(source, []).append({'run_id':folder.name, 'kind':kind})
        except (ValueError, OSError) as error:
            warnings.append(f'{folder.name}: {error}')
    return {'references':references, 'complete':not warnings, 'warnings':warnings,
            'scanned_manifests':count, 'missing_sources':sorted(set(references)-known),
            'scope':'Direct recovery/excerpt source references only; not project/queue/split or external references'}

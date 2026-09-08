"""Deterministic scene-grouped dataset splits without copying source samples."""
import hashlib
import json
import math


def verify_saved_split(saved, dataset_root):
    """Recompute assignment and metadata evidence without mutating the manifest."""
    if (not isinstance(saved, dict) or saved.get('schema_version') != 'carla-safety-split/0.1'
            or saved.get('verification') != 'finalized_manifest_and_temporal_index'
            or not isinstance(saved.get('datasets'), dict)):
        raise ValueError('Expected a metadata-verified split manifest')
    runs = []
    for run_id, evidence in saved['datasets'].items():
        if not isinstance(evidence, dict):
            raise ValueError('Invalid saved dataset evidence')
        runs.append({'run_id': run_id, 'scene_group': evidence.get('scene_group')})
    if 'ratios' not in saved or 'seed' not in saved:
        raise ValueError('Missing split configuration')
    current = verified_split(runs, dataset_root, saved['ratios'], saved['seed'])
    for key in ('assignments', 'scene_groups', 'run_count', 'group_count', 'datasets'):
        if current[key] != saved.get(key):
            raise ValueError(f'Split verification failed: {key} changed or inconsistent')
    return {'ok': True, 'run_count': current['run_count'],
            'verification': current['verification'], 'raw_sensor_files_verified': False}


def verified_split(runs, dataset_root, ratios=(0.8, 0.1, 0.1), seed=7):
    """Bind explicit grouping to finalized index metadata, not full sample validation."""
    from .replay import dataset_path
    from .data_quality import temporal_quality
    result = split_runs(runs, ratios, seed)
    evidence = {}
    for run in runs:
        run_id = run['run_id']
        folder = dataset_path(dataset_root, run_id)
        payloads = {}
        for name in ('manifest.json', 'index.json'):
            path = (folder / name).resolve()
            if path.parent != folder:
                raise ValueError(f'{run_id}: metadata outside dataset')
            payloads[name] = path.read_bytes()
        manifest = json.loads(payloads['manifest.json'])
        index = json.loads(payloads['index.json'])
        if manifest.get('run_id') != run_id or manifest.get('status') not in ('saved', 'saved_limit'):
            raise ValueError(f'{run_id}: dataset identity mismatch or recording not successfully finalized')
        frames = index.get('frames')
        count = manifest.get('frame_count')
        if (not isinstance(frames, list) or not frames or
                not all(isinstance(entry, dict) for entry in frames) or
                isinstance(count, bool) or not isinstance(count, int) or count != len(frames)):
            raise ValueError(f'{run_id}: invalid or inconsistent frame count')
        quality = temporal_quality(frames, manifest.get('sampling_every_frames'))
        if not quality['temporal_order_valid']:
            raise ValueError(f'{run_id}: invalid temporal index')
        evidence[run_id] = {'scene_group': run['scene_group'], 'frame_count': count,
            'execution_id': manifest.get('execution_id'), 'map': manifest.get('map'),
            'sha256': {name: hashlib.sha256(raw).hexdigest() for name, raw in payloads.items()},
            'temporal_quality': quality}
    result['datasets'] = evidence
    result['verification'] = 'finalized_manifest_and_temporal_index'
    result['notes'].append('Metadata hashes do not validate raw sensor files or prove scene independence.')
    return result


def split_runs(runs, ratios=(0.8,0.1,0.1), seed=7):
    if (len(ratios)!=3 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or
        not math.isfinite(v) or v<0 for v in ratios) or not math.isclose(sum(ratios),1)):
        raise ValueError('Three finite nonnegative split ratios must sum to one')
    if isinstance(seed,bool) or not isinstance(seed,int): raise ValueError('Seed must be an integer')
    groups={}; seen=set()
    for run in runs:
        run_id,group=run.get('run_id'),run.get('scene_group')
        if not isinstance(run_id,str) or not run_id.strip() or run_id in seen:
            raise ValueError('Run IDs must be nonempty and unique')
        if not isinstance(group,str) or not group.strip():
            raise ValueError('Explicit scene_group required; map or model name is not a scene identity')
        seen.add(run_id);groups.setdefault(group,[]).append(run_id)
    assignments={name:[] for name in ('train','validation','test')}
    group_assignments={}
    for group in sorted(groups):
        digest=hashlib.sha256(f'{seed}\0{group}'.encode()).digest()
        score=int.from_bytes(digest[:8],'big')/2**64
        name='train' if score<ratios[0] else 'validation' if score<ratios[0]+ratios[1] else 'test'
        assignments[name].extend(sorted(groups[group]));group_assignments[group]=name
    return {'schema_version':'carla-safety-split/0.1','seed':seed,'ratios':list(ratios),
            'assignments':assignments,'scene_groups':group_assignments,
            'run_count':len(seen),'group_count':len(groups),
            'notes':['Hash assignment keeps existing groups stable when new runs are added.',
                     'Ratios are probabilistic across groups; small datasets can have empty splits.',
                     'Explicit scene groups must include related variants to avoid leakage.']}

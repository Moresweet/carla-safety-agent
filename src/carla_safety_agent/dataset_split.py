"""Deterministic scene-grouped dataset splits without copying source samples."""
import hashlib
import math


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

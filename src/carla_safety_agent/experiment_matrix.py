"""Bounded immutable batch plans. Planning never mutates the simulator.

Dimension payloads are snapshots, not proof that dependencies are available.
The execution preflight must resolve and verify them before each job starts.
"""
import hashlib
import itertools
import json
import re
from pathlib import Path

AXES = ('scenes', 'models', 'weather', 'textures', 'seeds')
MAX_JOBS = 256
MAX_PLAN_BYTES = 16*1024*1024


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      allow_nan=False, separators=(',', ':')).encode('utf-8')


def compile_matrix(dimensions):
    if not isinstance(dimensions, dict) or set(dimensions) != set(AXES):
        raise ValueError('Specify scenes, models, weather, textures and seeds')
    # Detach caller-owned objects and reject non-JSON/non-finite values.
    payload = canonical(dimensions)
    if len(payload) > 8*1024*1024:
        raise ValueError('Experiment matrix exceeds 8 MiB')
    dimensions = json.loads(payload)
    count = 1
    for axis in AXES:
        values = dimensions[axis]
        if not isinstance(values, list) or not values:
            raise ValueError(f'Empty or invalid matrix axis: {axis}')
        count *= len(values)
        if count > MAX_JOBS:
            raise ValueError(f'Experiment matrix exceeds {MAX_JOBS} jobs')
        seen = set()
        for value in values:
            if axis == 'seeds':
                if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 2147483647:
                    raise ValueError('Seeds must be integers in 0..2147483647')
                identity = value
            else:
                if not isinstance(value, dict) or set(value) != {'id', 'configuration'}:
                    raise ValueError(f'{axis} variants require id and configuration')
                identity = value['id']
                if not isinstance(identity, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', identity):
                    raise ValueError('Invalid matrix variant ID')
                if not isinstance(value['configuration'], dict):
                    raise ValueError('Variant configuration must be an object')
            if identity in seen:
                raise ValueError(f'Duplicate variant in {axis}')
            seen.add(identity)
    jobs = []
    expanded_bytes = len(payload)
    for combination in itertools.product(*(dimensions[axis] for axis in AXES)):
        configuration = dict(zip(AXES, combination))
        job = {'job_id': hashlib.sha256(canonical(configuration)).hexdigest(),
               'configuration': configuration}
        expanded_bytes += len(canonical(job)) + 1
        if expanded_bytes > MAX_PLAN_BYTES:
            raise ValueError('Expanded experiment plan exceeds 16 MiB')
        jobs.append(job)
    document = {'schema_version': 'carla-experiment-matrix/1', 'dimensions': dimensions,
                'jobs': jobs, 'job_count': count, 'execution_status': 'not_started'}
    if len(canonical(document)) > MAX_PLAN_BYTES:
        raise ValueError('Expanded experiment plan exceeds 16 MiB')
    return document


def save_matrix(root, dimensions):
    document = compile_matrix(dimensions)
    payload = canonical(document)
    digest = hashlib.sha256(payload).hexdigest()
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    destination = root/f'matrix-{digest}.json'
    try:
        with destination.open('xb') as stream:
            stream.write(payload)
    except FileExistsError:
        if destination.is_symlink() or destination.read_bytes() != payload:
            raise ValueError('Existing matrix archive differs from content identity')
    return destination, digest

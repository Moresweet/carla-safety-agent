"""Content-addressed scenario plans; changing options never overwrites a plan."""
import hashlib
import json
import re
from pathlib import Path


def read_verified_scenario(path, expected=None):
    path = Path(path)
    if path.is_symlink() or path.stat().st_size > 8*1024*1024:
        raise ValueError('Invalid scenario archive path or size')
    payload = path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if path.name.startswith('plan-'):
        match = re.fullmatch(r'plan-([0-9a-f]{64})\.json', path.name)
        if not match or match.group(1) != digest:
            raise ValueError('Scenario archive content identity mismatch')
    if expected is not None and expected != digest:
        raise ValueError('Scenario changed after execution was requested')
    document = json.loads(payload)
    if not isinstance(document, dict):
        raise ValueError('Scenario must be an object')
    return document, digest


def archive_scenario(root, scenario):
    payload = json.dumps(scenario, sort_keys=True, ensure_ascii=False,
                         allow_nan=False, separators=(',', ':')).encode('utf-8')
    digest = hashlib.sha256(payload).hexdigest()
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    path = root/('plan-'+digest+'.json')
    try:
        with path.open('xb') as stream:
            stream.write(payload)
    except FileExistsError:
        if path.is_symlink() or path.read_bytes() != payload:
            raise ValueError('Existing scenario archive differs from its content identity')
    return path, digest

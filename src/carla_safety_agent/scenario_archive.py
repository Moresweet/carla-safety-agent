"""Content-addressed scenario plans; changing options never overwrites a plan."""
import hashlib
import json
from pathlib import Path


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

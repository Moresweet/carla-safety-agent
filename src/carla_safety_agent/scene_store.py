"""Versioned local scene documents, optimistic concurrency and immutable history."""
import copy
import fcntl
import json
import math
import re
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', value):
        raise ValueError('Invalid scene/version identifier')
    return value


def atomic(path, payload):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2))
    temporary.replace(path)


def validate_scene(document):
    document = copy.deepcopy(document)
    if not isinstance(document.get('map'), str) or not document['map']:
        raise ValueError('Scene map is required')
    objects = document.get('objects', [])
    if not isinstance(objects, list) or len(objects) > 2000:
        raise ValueError('Scene supports at most 2000 managed objects')
    seen = set()
    for obj in objects:
        stable = identifier(obj['stable_id'])
        if stable in seen: raise ValueError('Duplicate stable object ID')
        seen.add(stable)
        if not isinstance(obj.get('blueprint_id'), str): raise ValueError('Blueprint is required')
        for group, keys in [('location', ('x','y','z')), ('rotation', ('pitch','yaw','roll'))]:
            for key in keys:
                value = obj['transform'][group][key]
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise ValueError('Transforms must contain finite numbers')
    json.dumps(document, allow_nan=False)
    document['schema_version'] = 'carla-scene/1'
    return document


class SceneStore:
    def __init__(self, root):
        self.root = Path(root)

    @contextmanager
    def locked(self, scene_id):
        folder = self.root/identifier(scene_id)
        folder.mkdir(parents=True, exist_ok=True)
        with (folder/'.lock').open('a') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            yield folder

    def list(self):
        result = []
        for path in self.root.glob('*/head.json'):
            try: result.append(json.loads(path.read_text()))
            except (OSError, ValueError): continue
        return sorted(result, key=lambda v:v.get('updated_at',0), reverse=True)

    def read(self, scene_id, version=None):
        folder = self.root/identifier(scene_id)
        if not folder.is_dir(): raise ValueError('Scene not found')
        with self.locked(scene_id):
            head = json.loads((folder/'head.json').read_text())
            version = version or head['version']
            payload = json.loads((folder/(identifier(version)+'.json')).read_text())
            return {'head': head, 'document': payload}

    def save(self, document, name, scene_id=None, expected_version=None):
        document = validate_scene(document)
        if not str(name).strip() or len(str(name)) > 120: raise ValueError('Scene name is required, at most 120 characters')
        scene_id = scene_id or uuid.uuid4().hex
        with self.locked(scene_id) as folder:
            head_file = folder/'head.json'
            previous = json.loads(head_file.read_text()) if head_file.exists() else None
            if previous and expected_version != previous['version']:
                raise ValueError('Scene changed; reload before saving')
            version = uuid.uuid4().hex
            document.update(scene_id=scene_id, version=version, name=str(name), saved_at=time.time())
            atomic(folder/(version+'.json'), document)
            history = previous['history'][:previous['cursor']+1] if previous else []
            history.append(version)
            head = dict(scene_id=scene_id, name=str(name), version=version, history=history,
                        cursor=len(history)-1, updated_at=time.time(), map=document['map'],
                        object_count=len(document.get('objects', [])))
            atomic(head_file, head)
            return {'head': head, 'document': document}

    def move(self, scene_id, direction, expected_version):
        if direction not in (-1,1): raise ValueError('History direction must be -1 or 1')
        with self.locked(scene_id) as folder:
            head = json.loads((folder/'head.json').read_text())
            if expected_version != head['version']: raise ValueError('Scene changed; reload history')
            cursor = head['cursor']+direction
            if not 0 <= cursor < len(head['history']): raise ValueError('No earlier/later version')
            version = head['history'][cursor]
            document = json.loads((folder/(version+'.json')).read_text())
            head.update(cursor=cursor, version=version, name=document['name'], map=document['map'],
                        object_count=len(document.get('objects', [])), updated_at=time.time())
            atomic(folder/'head.json', head)
            return {'head': head, 'document': document}

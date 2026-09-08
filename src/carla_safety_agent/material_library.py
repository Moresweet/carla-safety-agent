"""Content-addressed textures and exported, exact component/slot metadata."""
import hashlib
import json
import re
import threading
from pathlib import Path
from .scene_store import atomic, identifier


def exact_environment_target(name, available):
    candidates = {name}
    for suffix in ('_SM_0', '_SM'):
        if name.endswith(suffix): candidates.add(name[:-len(suffix)])
    matches = candidates.intersection(available)
    if len(matches) != 1:
        raise ValueError('Environment material identity is missing or ambiguous; refusing prefix matching')
    return matches.pop()


def material_edits(records):
    """Validate persisted references before touching the simulator."""
    if not isinstance(records, list) or len(records) > 2000:
        raise ValueError('At most 2000 material overrides are supported')
    result = {}
    for record in records:
        if not isinstance(record, dict): raise ValueError('Invalid material override')
        target, component, slot, texture = (record.get(k) for k in ('target','component','slot','texture'))
        if any(not isinstance(v, str) or not v or '|' in v for v in (target, component)):
            raise ValueError('Invalid material identity')
        if isinstance(slot, bool) or not isinstance(slot, int) or slot < 0:
            raise ValueError('Invalid material slot')
        if not isinstance(texture, str) or not re.fullmatch(r'[a-f0-9]{64}', texture):
            raise ValueError('Invalid texture digest')
        key = (target, component, slot)
        if key in result: raise ValueError('Duplicate material override')
        result[key] = texture
    return result


class MaterialTransaction:
    """Caller preflights every reference and compensates on any later failure."""
    def __init__(self, before, desired, apply):
        self.before = material_edits(before)
        self.desired = material_edits(desired)
        self.apply_one = apply
        self.changed = [k for k in sorted(self.before.keys() | self.desired.keys())
                        if self.before.get(k) != self.desired.get(k)]
        self.attempted = []

    def apply(self):
        for key in self.changed:
            self.attempted.append(key)
            self.apply_one(key, self.desired.get(key))

    def rollback(self):
        failures = []
        for key in reversed(self.attempted):
            try: self.apply_one(key, self.before.get(key))
            except Exception as exc: failures.append(f'{key}: {exc}')
        if failures: raise RuntimeError('Material rollback incomplete: ' + '; '.join(failures))
        self.attempted.clear()


class MaterialLibrary:
    def __init__(self, root):
        self.root = Path(root)
        self.lock = threading.RLock()

    def catalog(self, map_name):
        town = identifier(map_name.split('/')[-1])
        path = self.root/'material-exports'/town/'preview-catalog.json'
        return json.loads(path.read_text()) if path.is_file() else {'actors':{}, 'map':map_name}

    def mesh(self, town, filename):
        catalog = self.catalog(identifier(town))
        allowed = {s.get('mesh_file') for entries in catalog['actors'].values() for entry in entries for s in entry['slots']}
        if filename not in allowed or not filename or Path(filename).name != filename:
            raise ValueError('Unknown exported material mesh')
        folder = (self.root/'material-exports'/town).resolve()
        path = (folder/filename).resolve()
        if path.parent != folder: raise ValueError('Mesh path leaves catalog')
        return path

    def put_texture(self, payload):
        digest = hashlib.sha256(payload).hexdigest()
        folder = self.root/'textures'
        folder.mkdir(parents=True, exist_ok=True)
        path = folder/(digest+'.png')
        with self.lock:
            if not path.exists():
                temporary = path.with_suffix('.tmp')
                temporary.write_bytes(payload)
                temporary.replace(path)
        return digest

    def texture(self, digest):
        if not re.fullmatch(r'[a-f0-9]{64}', digest): raise ValueError('Invalid texture digest')
        path = self.root/'textures'/(digest+'.png')
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != digest: raise ValueError('Texture checksum mismatch')
        return payload

    def overrides(self, episode):
        with self.lock:
            path = self.root/'material-overrides.json'
            return json.loads(path.read_text()).get(str(episode), {}) if path.is_file() else {}

    def record(self, episode, target, component, slot, texture):
        with self.lock:
            path = self.root/'material-overrides.json'
            self.root.mkdir(parents=True, exist_ok=True)
            data = json.loads(path.read_text()) if path.is_file() else {}
            edits = data.setdefault(str(episode), {})
            key = json.dumps([target,component,int(slot)])
            if texture is None: edits.pop(key, None)
            else: edits[key] = {'target':target,'component':component,'slot':int(slot),'texture':texture}
            atomic(path,data)

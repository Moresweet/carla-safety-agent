"""Versioned local scene documents, optimistic concurrency and immutable history."""
import copy
import fcntl
import json
import math
import os
import re
import stat
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', value):
        raise ValueError('Invalid scene/version identifier')
    return value


def atomic(path, payload):
    if path.is_symlink():raise ValueError('Refusing to replace a linked state file')
    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2).encode('utf-8')
    temporary = path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    with temporary.open('xb') as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    except OSError as exc:
        raise OSError('State file was replaced but directory sync failed; inspect current state before retrying') from exc
    finally: os.close(descriptor)


def read_json(path, max_bytes=16*1024*1024):
    """Bounded regular-file reads; reject duplicate keys and special JSON numbers."""
    def pairs(items):
        result={}
        for key,value in items:
            if key in result: raise ValueError('Duplicate scene JSON key')
            result[key]=value
        return result
    def invalid(value): raise ValueError('Non-finite scene JSON number: '+value)
    if path.is_symlink(): raise ValueError('Scene files must not be symbolic links')
    descriptor=os.open(path,os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor,'rb') as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size>max_bytes:
            raise ValueError('Invalid scene file type or size')
        raw=stream.read(max_bytes+1)
    if len(raw)>max_bytes: raise ValueError('Scene file exceeds size limit')
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=invalid)


def finite_number(value):
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def validate_transform_patch(transform):
    if not isinstance(transform,dict) or set(transform)-{'location','rotation'}:
        raise ValueError('Transform patch must contain location or rotation')
    for group, keys in [('location',{'x','y','z'}),('rotation',{'pitch','yaw','roll'})]:
        values=transform.get(group,{})
        if not isinstance(values,dict) or set(values)-keys:
            raise ValueError('Unknown transform component')
        if not all(finite_number(value) for value in values.values()):
            raise ValueError('Transforms must contain finite numbers')


def validate_transform(transform):
    if not isinstance(transform, dict): raise ValueError('Transform must be an object')
    for group, keys in [('location', ('x','y','z')), ('rotation', ('pitch','yaw','roll'))]:
        values = transform.get(group)
        if not isinstance(values, dict) or set(values) != set(keys):
            raise ValueError('Transform requires complete location and rotation')
        if not all(finite_number(value) for value in values.values()):
            raise ValueError('Transforms must contain finite numbers')


def validate_scene(document):
    if not isinstance(document, dict): raise ValueError('Scene must be an object')
    document = copy.deepcopy(document)
    if document.get('schema_version', 'carla-scene/1') != 'carla-scene/1':
        raise ValueError('Unsupported scene schema version')
    if not isinstance(document.get('map'), str) or not document['map']:
        raise ValueError('Scene map is required')
    objects = document.get('objects', [])
    if not isinstance(objects, list) or len(objects) > 2000:
        raise ValueError('Scene supports at most 2000 managed objects')
    seen = set()
    for obj in objects:
        if not isinstance(obj, dict): raise ValueError('Invalid scene object')
        stable = identifier(obj.get('stable_id'))
        if stable in seen: raise ValueError('Duplicate stable object ID')
        seen.add(stable)
        if not isinstance(obj.get('blueprint_id'), str) or not obj['blueprint_id']:
            raise ValueError('Blueprint is required')
        validate_transform(obj.get('transform'))
        options = obj.get('spawn_options', {})
        if not isinstance(options, dict) or set(options) - {'mass', 'scale'}:
            raise ValueError('Unsupported spawn options')
        for key, value in options.items():
            if not finite_number(value) or value < 0 or (key == 'scale' and value == 0):
                raise ValueError('Invalid mass or scale')
    document['objects'] = objects
    if 'actor_materials' in document:
        from .actor_materials import actor_material_edits
        actor_material_edits(document['actor_materials'],objects)
    if 'spectator' in document: validate_transform(document['spectator'])
    weather = document.get('weather', {})
    if not isinstance(weather, dict) or not all(
            isinstance(key, str) and re.fullmatch(r'[a-z][a-z_]*', key) and finite_number(value)
            for key, value in weather.items()):
        raise ValueError('Invalid weather properties')
    json.dumps(document, allow_nan=False)
    document['schema_version'] = 'carla-scene/1'
    return document


class SceneStore:
    def __init__(self, root):
        self.root = Path(root)

    def folder(self, scene_id):
        folder=self.root/identifier(scene_id)
        if folder.is_symlink() or folder.resolve().parent!=self.root.resolve():
            raise ValueError('Scene directory is outside the configured store')
        return folder

    def head(self, folder, scene_id):
        head=read_json(folder/'head.json')
        if not isinstance(head,dict) or head.get('scene_id')!=scene_id:
            raise ValueError('Scene head identity mismatch')
        history=head.get('history');cursor=head.get('cursor')
        if (not isinstance(history,list) or not 1<=len(history)<=10000 or
                any(not isinstance(value,str) for value in history) or len(set(history))!=len(history) or
                type(cursor) is not int or not 0<=cursor<len(history)):
            raise ValueError('Invalid scene history')
        for version in history: identifier(version)
        if head.get('version')!=history[cursor]: raise ValueError('Scene history cursor mismatch')
        if (not isinstance(head.get('name'),str) or not head['name'].strip() or len(head['name'])>120 or
                not isinstance(head.get('map'),str) or not head['map'] or
                type(head.get('object_count')) is not int or not 0<=head['object_count']<=2000 or
                not finite_number(head.get('updated_at'))):
            raise ValueError('Invalid scene head metadata')
        return head

    def document(self, folder, scene_id, version):
        document=validate_scene(read_json(folder/(identifier(version)+'.json')))
        if document.get('scene_id')!=scene_id or document.get('version')!=version:
            raise ValueError('Scene version identity mismatch')
        if not isinstance(document.get('name'),str) or not document['name'].strip() or len(document['name'])>120:
            raise ValueError('Invalid scene version name')
        if not finite_number(document.get('saved_at')):raise ValueError('Invalid scene save timestamp')
        return document

    @staticmethod
    def verify_current(head, document):
        if (head['name']!=document['name'] or head['map']!=document['map'] or
                head['object_count']!=len(document['objects'])):
            raise ValueError('Scene head metadata differs from its current version')

    @contextmanager
    def locked(self, scene_id):
        folder = self.folder(scene_id)
        existed=folder.exists()
        folder.mkdir(parents=True, exist_ok=True)
        if not existed:
            parent=os.open(folder.parent,os.O_RDONLY | os.O_DIRECTORY)
            try:os.fsync(parent)
            finally:os.close(parent)
        if (folder/'.lock').is_symlink():raise ValueError('Scene lock must not be a symbolic link')
        descriptor=os.open(folder/'.lock',os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,0o600)
        with os.fdopen(descriptor,'a') as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):raise ValueError('Invalid scene lock type')
            fcntl.flock(stream, fcntl.LOCK_EX)
            yield folder

    def list(self):
        result = []
        for path in self.root.glob('*/head.json'):
            try: result.append(self.head(self.folder(path.parent.name),path.parent.name))
            except (OSError, ValueError): continue
        return sorted(result, key=lambda v:v.get('updated_at',0), reverse=True)

    def read(self, scene_id, version=None):
        folder = self.folder(scene_id)
        if not folder.is_dir(): raise ValueError('Scene not found')
        with self.locked(scene_id):
            head = self.head(folder,scene_id)
            version = version or head['version']
            payload = self.document(folder,scene_id,version)
            if version==head['version']:self.verify_current(head,payload)
            return {'head': head, 'document': payload}

    def save(self, document, name, scene_id=None, expected_version=None):
        document = validate_scene(document)
        if not str(name).strip() or len(str(name)) > 120: raise ValueError('Scene name is required, at most 120 characters')
        scene_id = scene_id or uuid.uuid4().hex
        with self.locked(scene_id) as folder:
            head_file = folder/'head.json'
            previous = self.head(folder,scene_id) if head_file.exists() or head_file.is_symlink() else None
            if previous and expected_version != previous['version']:
                raise ValueError('Scene changed; reload before saving')
            if previous:self.verify_current(previous,self.document(folder,scene_id,previous['version']))
            if previous and previous['cursor']>=9999:raise ValueError('Scene history limit reached')
            version = uuid.uuid4().hex
            document.update(scene_id=scene_id, version=version, name=str(name), saved_at=time.time())
            destination=folder/(version+'.json')
            if destination.exists() or destination.is_symlink():raise ValueError('Scene version already exists')
            atomic(destination, document)
            history = previous['history'][:previous['cursor']+1] if previous else []
            history.append(version)
            head = dict(scene_id=scene_id, name=str(name), version=version, history=history,
                        cursor=len(history)-1, updated_at=time.time(), map=document['map'],
                        object_count=len(document.get('objects', [])))
            atomic(head_file, head)
            return {'head': head, 'document': document}

    def move(self, scene_id, direction, expected_version):
        if type(direction) is not int or direction not in (-1,1): raise ValueError('History direction must be -1 or 1')
        with self.locked(scene_id) as folder:
            head = self.head(folder,scene_id)
            if expected_version != head['version']: raise ValueError('Scene changed; reload history')
            cursor = head['cursor']+direction
            if not 0 <= cursor < len(head['history']): raise ValueError('No earlier/later version')
            version = head['history'][cursor]
            # Reject corrupted history before changing the durable cursor. The
            # world restore preflight runs later and cannot protect this write.
            document = self.document(folder,scene_id,version)
            head.update(cursor=cursor, version=version, name=document['name'], map=document['map'],
                        object_count=len(document.get('objects', [])), updated_at=time.time())
            atomic(folder/'head.json', head)
            return {'head': head, 'document': document}

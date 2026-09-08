"""Durable studio-owned environment visibility (not inferred external state)."""
import json
import threading
from pathlib import Path
from .scene_store import atomic


def hidden_records(records):
    if not isinstance(records, list) or len(records) > 20000:
        raise ValueError('Invalid hidden environment objects')
    result = {}
    for record in records:
        if not isinstance(record, dict): raise ValueError('Invalid hidden object')
        object_id, name = record.get('object_id'), record.get('name')
        if not isinstance(object_id, str) or not object_id.isdigit() or not 0 <= int(object_id) < 2**64:
            raise ValueError('Invalid environment object ID')
        if not isinstance(name, str) or not name: raise ValueError('Environment name is required')
        if object_id in result: raise ValueError('Duplicate hidden environment object')
        result[object_id] = {'object_id': object_id, 'name': name}
    return result


class VisibilityStore:
    def __init__(self, root):
        self.path = Path(root)/'visibility.json'
        self.lock = threading.RLock()

    def records(self, episode):
        with self.lock:
            data = json.loads(self.path.read_text()) if self.path.exists() else {}
            return list(hidden_records(data.get(str(episode), [])).values())

    def record(self, episode, object_id, name, visible):
        if not isinstance(visible, bool): raise ValueError('Visibility must be boolean')
        item = hidden_records([{'object_id':str(object_id), 'name':name}])
        with self.lock:
            data = json.loads(self.path.read_text()) if self.path.exists() else {}
            records = hidden_records(data.get(str(episode), []))
            if visible: records.pop(str(object_id), None)
            else: records.update(item)
            data[str(episode)] = list(records.values())
            self.path.parent.mkdir(parents=True, exist_ok=True)
            atomic(self.path, data)


class VisibilityTransaction:
    def __init__(self, previous, desired, resolve, apply):
        self.previous, self.desired = hidden_records(previous), hidden_records(desired)
        self.apply_one, self.attempted = apply, []
        self.changed = sorted(self.previous.keys() ^ self.desired.keys())
        # Validate all saved identities, including objects already hidden.
        for record in list(self.previous.values()) + list(self.desired.values()):
            actual_name = resolve(int(record['object_id']))
            if actual_name != record['name']:
                raise ValueError('Environment identity changed; refusing visibility restore')

    def apply(self):
        for key in self.changed:
            self.attempted.append(key)
            record = self.desired.get(key, self.previous.get(key))
            self.apply_one(record, key not in self.desired)

    def rollback(self):
        errors = []
        for key in reversed(self.attempted):
            record = self.previous.get(key, self.desired.get(key))
            try: self.apply_one(record, key not in self.previous)
            except Exception as exc: errors.append(str(exc))
        if errors: raise RuntimeError('Visibility rollback incomplete: ' + '; '.join(errors))
        self.attempted.clear()

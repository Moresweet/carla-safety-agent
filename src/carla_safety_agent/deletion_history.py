"""Durable deletion intent: an interrupted write never implies native success."""
from pathlib import Path
import time
import uuid
from .scene_store import atomic, identifier, read_json, finite_number


class DeletionHistory:
    def __init__(self, root):
        self.root = Path(root)

    def path(self, operation_id):
        identifier(operation_id)
        path = self.root / (operation_id + '.json')
        if self.root.is_symlink() or path.is_symlink():
            raise ValueError('Linked deletion history refused')
        return path

    def begin(self, episode, actor_id, type_id, backup):
        if type(actor_id) is not int or actor_id <= 0 or type(episode) is not int:
            raise ValueError('Invalid deletion identity')
        if not isinstance(type_id, str) or not type_id:
            raise ValueError('Missing deletion type')
        selected = {key: identifier(backup[key]) for key in ('scene_id', 'version', 'stable_id')}
        operation_id = uuid.uuid4().hex
        path = self.path(operation_id)
        self.root.mkdir(parents=True, exist_ok=True)
        row = {'schema_version': 'carla-deletion-history/1', 'operation_id': operation_id,
               'episode': episode, 'actor_id': actor_id, 'type_id': type_id,
               'backup': selected, 'state': 'attempting', 'created_at': time.time()}
        atomic(path, row)
        return operation_id

    def finish(self, operation_id, error=None):
        path = self.path(operation_id)
        row = self.read(operation_id)
        if row.get('operation_id') != operation_id or row.get('state') != 'attempting':
            raise ValueError('Deletion intent changed; inspect before further action')
        row.update(state='confirmed' if error is None else 'needs_attention',
                   finished_at=time.time(), error=None if error is None else str(error)[:2000])
        atomic(path, row)
        return row

    def read(self, operation_id):
        row = read_json(self.path(operation_id), max_bytes=64*1024)
        if (not isinstance(row, dict) or row.get('schema_version') != 'carla-deletion-history/1'
                or row.get('operation_id') != operation_id
                or row.get('state') not in ('attempting', 'confirmed', 'needs_attention')):
            raise ValueError('Invalid deletion history identity or state')
        if (type(row.get('episode')) is not int or type(row.get('actor_id')) is not int
                or row['actor_id'] <= 0 or not isinstance(row.get('type_id'), str) or not row['type_id']
                or not finite_number(row.get('created_at')) or row['created_at'] < 0):
            raise ValueError('Invalid deletion history metadata')
        backup = row.get('backup')
        if not isinstance(backup, dict) or set(backup) != {'scene_id','version','stable_id'}:
            raise ValueError('Invalid deletion backup')
        for value in backup.values(): identifier(value)
        if row['state'] != 'attempting':
            if not finite_number(row.get('finished_at')) or row['finished_at'] < 0:
                raise ValueError('Invalid deletion completion time')
            if row['state'] == 'confirmed' and row.get('error') is not None:
                raise ValueError('Confirmed deletion contains an error')
            if row['state'] == 'needs_attention' and not isinstance(row.get('error'), str):
                raise ValueError('Missing deletion inspection reason')
        return row

    def list(self, limit=50):
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError('Deletion history limit must be 1..200')
        if self.root.is_symlink(): raise ValueError('Linked deletion history refused')
        rows, warnings = [], []
        if self.root.exists():
            for count, path in enumerate(self.root.glob('*.json')):
                if count >= 10000:
                    raise ValueError('Deletion history scan limit exceeded; archive before listing')
                try:
                    rows.append(self.read(path.stem))
                except (ValueError, OSError) as error:
                    warnings.append({'operation_id': path.stem, 'error': str(error)})
        rows.sort(key=lambda row: (row['created_at'], row['operation_id']), reverse=True)
        return {'entries': rows[:limit], 'total': len(rows), 'truncated': len(rows)>limit,
                'complete': not warnings, 'warnings': warnings,
                'scope': 'historical deletion observations; not current world state or automatic restore approval'}

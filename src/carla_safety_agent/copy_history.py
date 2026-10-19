"""Write-ahead copy receipts; interrupted operations require inspection."""
import time
import uuid
import threading
import copy
from pathlib import Path
from .scene_store import atomic, identifier, read_json


class CopyHistory:
    def __init__(self, root):
        self.root = Path(root)
        self.lock = threading.RLock()

    def undo(self, operation_id, verify, delete):
        """Verify exact target before journaling intent; never retry uncertain deletion."""
        with self.lock:
            row = self.read(operation_id)
            if row['state'] != 'confirmed' or row.get('undo') is not None:
                raise ValueError('Copy is not eligible for undo; inspect its history')
            verify(row['target'])
            row['undo'] = {'state':'attempting', 'started_at':time.time()}
            atomic(self.path(operation_id), row)
            try:
                result = delete(row['target'])
                if (not isinstance(result, dict) or result.get('ok') is not True
                        or result.get('actor_id') != row['target']['actor_id']
                        or not result.get('backup') or not result.get('operation_id')):
                    raise ValueError('Deletion was not confirmed with a recovery backup')
                row['undo'].update(state='confirmed', finished_at=time.time(), deletion=result)
                atomic(self.path(operation_id), row)
                return {'ok':True, 'copy_operation_id':operation_id, 'deletion':result}
            except Exception as error:
                row['undo'].update(state='needs_attention', finished_at=time.time(), error=str(error)[:2000])
                try:
                    atomic(self.path(operation_id), row)
                except Exception as journal_error:
                    raise RuntimeError(f'Copy undo {operation_id} journal failed: {journal_error}') from error
                raise RuntimeError(f'Copy undo {operation_id} requires inspection: {error}') from error

    def redo(self, operation_id, deletion_id, verify, restore, identify):
        """Restore the exact last deletion backup and retain prior undo cycles."""
        with self.lock:
            row = self.read(operation_id)
            undo = row.get('undo')
            if (row['state'] != 'confirmed' or not undo or undo['state'] != 'confirmed'
                    or row.get('redo') is not None):
                raise ValueError('Copy is not eligible for redo; inspect its history')
            deletion = undo.get('deletion', {})
            if deletion.get('operation_id') != deletion_id:
                raise ValueError('Copy undo cycle changed; refresh before redo')
            backup = deletion.get('backup', {})
            selection = {key:identifier(backup.get(key)) for key in ('scene_id','version','stable_id')}
            if selection['stable_id'] != row['target']['stable_id']:
                raise ValueError('Copy restore backup identity mismatch')
            if len(row.get('cycles', [])) >= 50:
                raise ValueError('Copy history cycle limit reached; preserve and inspect history')
            verify(row['target'], selection)
            row['redo'] = {'state':'attempting','started_at':time.time(),'selection':selection}
            atomic(self.path(operation_id), row)
            try:
                result = restore(selection)
                target = identify(result, selection)
                self.validate_identity(target, managed=True)
                if (target['stable_id'] != row['target']['stable_id']
                        or target['episode'] != row['target']['episode']
                        or target['type_id'] != row['target']['type_id']
                        or target['actor_id'] in (row['target']['actor_id'],row['identity']['actor_id'])):
                    raise ValueError('Restored copy identity differs from its backup')
                completed = copy.deepcopy(row)
                completed['redo'].update(state='confirmed',finished_at=time.time(),target=target)
                completed.setdefault('cycles', []).append({'target':completed['target'],
                    'undo':completed.pop('undo'),'redo':completed.pop('redo')})
                completed.update(target=target,target_actor_id=target['actor_id'])
                atomic(self.path(operation_id), completed)
                return {'ok':True,'copy_operation_id':operation_id,'target':target,'restoration':result}
            except Exception as error:
                row['redo'].update(state='needs_attention',finished_at=time.time(),error=str(error)[:2000])
                try:
                    atomic(self.path(operation_id), row)
                except Exception as journal_error:
                    raise RuntimeError(f'Copy redo {operation_id} journal failed: {journal_error}') from error
                raise RuntimeError(f'Copy redo {operation_id} requires inspection: {error}') from error

    def path(self, operation_id):
        identifier(operation_id)
        path = self.root / (operation_id + '.json')
        if self.root.is_symlink() or path.is_symlink():
            raise ValueError('Linked copy journal refused')
        return path

    def execute(self, source, action, identify):
        self.validate_identity(source, managed=False)
        operation_id = uuid.uuid4().hex
        row = dict(schema_version='carla-copy-history/1', operation_id=operation_id,
                   kind='copy', created_at=time.time(), state='attempting',
                   identity=source, target=None, error=None)
        path = self.path(operation_id)
        self.root.mkdir(parents=True, exist_ok=True)
        atomic(path, row)  # No native operation if intent cannot be saved.
        try:
            result = action()
            # Preserve returned native ID even if subsequent provenance lookup fails.
            row['target_actor_id'] = result['object']['id']
            atomic(path, row)
            target = identify(result)
            self.validate_identity(target, managed=True)
            if target['episode'] != source['episode'] or target['actor_id'] == source['actor_id']:
                raise ValueError('Copy target identity conflicts with source')
            row.update(state='confirmed', target=target, finished_at=time.time())
            atomic(path, row)
            return {**result, 'copy_operation_id':operation_id}
        except Exception as error:
            row.update(state='needs_attention', error=str(error)[:2000], finished_at=time.time())
            try:
                atomic(path, row)
            except Exception as journal_error:
                raise RuntimeError(f'Copy {operation_id} requires inspection; journal failed: {journal_error}') from error
            raise RuntimeError(f'Copy {operation_id} requires inspection: {error}') from error

    @staticmethod
    def validate_identity(value, managed):
        if (not isinstance(value, dict) or set(value) != {'episode','actor_id','type_id','stable_id'}
                or not isinstance(value['episode'], str) or not value['episode'].isdigit()
                or type(value['actor_id']) is not int or value['actor_id'] <= 0
                or not isinstance(value['type_id'], str) or not value['type_id']):
            raise ValueError('Invalid copy identity')
        if managed or value['stable_id'] is not None:
            identifier(value['stable_id'])

    def read(self, operation_id):
        row = read_json(self.path(operation_id), max_bytes=1024*1024)
        if (not isinstance(row, dict) or row.get('schema_version') != 'carla-copy-history/1'
                or row.get('operation_id') != operation_id or row.get('kind') != 'copy'
                or row.get('state') not in ('attempting','confirmed','needs_attention')):
            raise ValueError('Invalid copy journal')
        self.validate_identity(row.get('identity'), managed=False)
        from .scene_store import finite_number
        if not finite_number(row.get('created_at')) or row['created_at'] < 0:
            raise ValueError('Invalid copy time')
        if row['state'] == 'confirmed':
            self.validate_identity(row.get('target'), managed=True)
            if (row['target']['episode'] != row['identity']['episode']
                    or row['target']['actor_id'] == row['identity']['actor_id']
                    or row.get('target_actor_id') != row['target']['actor_id']):
                raise ValueError('Copy target conflicts with recorded identity')
        undo = row.get('undo')
        if undo is not None:
            if (row['state'] != 'confirmed' or not isinstance(undo, dict)
                    or undo.get('state') not in ('attempting','confirmed','needs_attention')
                    or not finite_number(undo.get('started_at'))):
                raise ValueError('Invalid copy undo intent')
        redo = row.get('redo')
        if redo is not None and (not undo or undo['state'] != 'confirmed'
                or not isinstance(redo,dict) or redo.get('state') not in ('attempting','needs_attention')
                or not finite_number(redo.get('started_at'))):
            raise ValueError('Invalid copy redo intent')
        cycles=row.get('cycles',[])
        if not isinstance(cycles,list) or len(cycles)>50:
            raise ValueError('Invalid copy history cycles')
        for cycle in cycles:
            if (not isinstance(cycle,dict) or set(cycle)!={'target','undo','redo'}
                    or not isinstance(cycle['undo'],dict) or cycle['undo'].get('state')!='confirmed'
                    or not isinstance(cycle['redo'],dict) or cycle['redo'].get('state')!='confirmed'):
                raise ValueError('Invalid completed copy cycle')
            self.validate_identity(cycle['target'],managed=True)
            self.validate_identity(cycle['redo'].get('target'),managed=True)
        return row

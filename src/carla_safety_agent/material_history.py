"""Write-ahead exact environment-slot edits; no claim to observe GPU state."""
import re
import time
import uuid
import threading
import copy
import hashlib
import json
from pathlib import Path
from .scene_store import atomic, identifier, read_json


def validate_identity(value):
    if not isinstance(value,dict) or set(value)!={'episode','object_id','target','component','slot'}:
        raise ValueError('Exact material history identity required')
    if not isinstance(value['episode'],str) or not value['episode'].isascii() or not value['episode'].isdigit():
        raise ValueError('Invalid material episode')
    if not isinstance(value['object_id'],str) or not value['object_id'].isascii() or not value['object_id'].isdigit():
        raise ValueError('Invalid material object ID')
    if type(value['slot']) is not int or value['slot']<0:
        raise ValueError('Invalid material slot')
    if any(not isinstance(value[k],str) or not value[k] or '|' in value[k] for k in ('target','component')):
        raise ValueError('Invalid material target')


def validate_texture(value):
    if value is not None and (not isinstance(value,str) or not re.fullmatch('[a-f0-9]{64}',value)):
        raise ValueError('Invalid material history texture')


class MaterialHistory:
    def __init__(self,root):self.root=Path(root);self.lock=threading.RLock()

    @staticmethod
    def inspection_token(row):
        return hashlib.sha256(json.dumps(row,sort_keys=True,separators=(',',':')).encode()).hexdigest()

    def recover(self,operation_id,token,choice,registered,verify,apply):
        """Explicit new write after inspection, retaining the original failure."""
        with self.lock:
            row=self.read(operation_id)
            if (choice not in ('source','target') or token!=self.inspection_token(row)
                    or row.get('recovery') is not None
                    or (row['state']=='confirmed' and row.get('pending') is None)):
                raise ValueError('Material recovery requires a fresh unresolved inspection')
            validate_texture(registered)
            pending=row.get('pending')
            desired=(pending[choice] if pending else row['before' if choice=='source' else 'after'])
            verify(row['identity'],registered,desired)
            row['recovery']=dict(state='attempting',choice=choice,registered_before=registered,
                desired=desired,started_at=time.time())
            atomic(self.path(operation_id),row)
            try:
                apply(row['identity'],desired)
                row['recovery'].update(state='confirmed',finished_at=time.time())
                atomic(self.path(operation_id),row)
                return row
            except Exception as error:
                row['recovery'].update(state='needs_attention',error=str(error)[:2000],finished_at=time.time())
                try:atomic(self.path(operation_id),row)
                except Exception as journal_error:
                    raise RuntimeError(f'Material recovery {operation_id} journal failed: {journal_error}') from error
                raise RuntimeError(f'Material recovery {operation_id} requires inspection: {error}') from error

    def inspect(self,operation_id,observe):
        """Compare the registry, never resolve an uncertain native operation."""
        with self.lock:
            row=self.read(operation_id)
            current=observe(row['identity'])
            validate_texture(current)
            pending=row.get('pending')
            source=pending['source'] if pending else row['before']
            target=pending['target'] if pending else row['after']
            matches=('both' if current==source==target else 'target' if current==target
                     else 'source' if current==source else 'neither')
            return dict(operation_id=operation_id,revision=row.get('revision',operation_id),
                inspection_token=self.inspection_token(row),recovery=row.get('recovery'),
                state=row['state'],pending=pending,identity=row['identity'],registered_texture=current,
                source=source,target=target,registry_matches=matches,
                native_verified=False,automatic_retry_allowed=False,
                note='Registry observation only; native/GPU state is not readable here. '
                     'History is unchanged; matching a reference does not resolve an uncertain operation.')

    def transition(self,operation_id,direction,revision,verify,apply):
        with self.lock:
            row=self.read(operation_id)
            if (direction not in ('undo','redo') or row['state']!='confirmed'
                    or row.get('pending') is not None or revision!=row.get('revision',operation_id)):
                raise ValueError('Material history changed or needs inspection')
            applied=row.get('applied',True)
            if applied!=(direction=='undo'):raise ValueError('Material history direction is unavailable')
            if len(row.get('transitions',[]))>=100:raise ValueError('Material history transition limit reached')
            self.require_resolved_slot(row['identity'])
            source,target=(row['after'],row['before']) if applied else (row['before'],row['after'])
            verify(row['identity'],source,target)
            row['pending']=dict(direction=direction,source=source,target=target,state='attempting',started_at=time.time())
            atomic(self.path(operation_id),row)
            try:
                apply(row['identity'],target)
                done=copy.deepcopy(row)
                pending=done.pop('pending');pending.update(state='confirmed',finished_at=time.time())
                done.setdefault('transitions',[]).append(pending)
                done.update(applied=not applied,revision=uuid.uuid4().hex)
                atomic(self.path(operation_id),done)
                return done
            except Exception as error:
                row['pending'].update(state='needs_attention',error=str(error)[:2000])
                try:atomic(self.path(operation_id),row)
                except Exception as journal_error:
                    raise RuntimeError(f'Material history {operation_id} journal failed: {journal_error}') from error
                raise RuntimeError(f'Material history {operation_id} requires inspection: {error}') from error

    def path(self,operation_id):
        identifier(operation_id)
        path=self.root/(operation_id+'.json')
        if self.root.is_symlink() or path.is_symlink():raise ValueError('Linked material history refused')
        return path

    def execute(self,identity,before,after,apply):
        # Serialize new edits with transition/recovery on this journal instance.
        with self.lock:
            return self._execute(identity,before,after,apply)

    def require_resolved_slot(self, identity):
        """Caller must serialize this check with the subsequent native edit."""
        if self.root.is_symlink():
            raise ValueError('Linked material history refused')
        for count, path in enumerate(self.root.glob('*.json')):
            if count >= 10000:
                raise ValueError('Material history scan limit exceeded')
            try:
                previous = self.read(path.stem)
            except (ValueError, OSError) as error:
                raise ValueError(f'Material journal {path.name} cannot be verified; '
                                 f'new edits stopped without deleting history: {error}') from error
            if previous['identity'] != identity:
                continue
            recovery = previous.get('recovery')
            if recovery is not None and recovery['state'] == 'confirmed':
                continue
            if (previous['state'] != 'confirmed' or previous.get('pending') is not None
                    or recovery is not None):
                raise ValueError(f'Material slot has an unresolved operation {previous["operation_id"]}; '
                                 'open this operation in Editor History, inspect and explicitly recover it first')

    def _execute(self,identity,before,after,apply):
        validate_identity(identity);validate_texture(before);validate_texture(after)
        self.require_resolved_slot(identity)
        operation_id=uuid.uuid4().hex
        row=dict(schema_version='carla-material-history/1',operation_id=operation_id,
            kind='material',identity=dict(identity),before=before,after=after,
            state='attempting',created_at=time.time())
        path=self.path(operation_id);self.root.mkdir(parents=True,exist_ok=True)
        atomic(path,row)
        try:
            apply()
            row.update(state='confirmed',finished_at=time.time())
            atomic(path,row)
        except Exception as error:
            row.update(state='needs_attention',finished_at=time.time(),error=str(error)[:2000])
            try:atomic(path,row)
            except Exception as journal_error:
                raise RuntimeError(f'Material edit {operation_id} journal failed: {journal_error}') from error
            raise RuntimeError(f'Material edit {operation_id} requires inspection: {error}') from error
        return operation_id

    def read(self,operation_id):
        row=read_json(self.path(operation_id),max_bytes=64*1024)
        if (not isinstance(row,dict) or row.get('schema_version')!='carla-material-history/1'
                or row.get('kind')!='material' or row.get('operation_id')!=operation_id
                or row.get('state') not in ('attempting','confirmed','needs_attention')):
            raise ValueError('Invalid material history record')
        validate_identity(row.get('identity'));validate_texture(row.get('before'));validate_texture(row.get('after'))
        from .scene_store import finite_number
        if not finite_number(row.get('created_at')) or row['created_at']<0:raise ValueError('Invalid material history time')
        if type(row.get('applied',True)) is not bool:raise ValueError('Invalid material applied state')
        if 'revision' in row:identifier(row['revision'])
        transitions=row.get('transitions',[])
        if not isinstance(transitions,list) or len(transitions)>100:raise ValueError('Invalid material transitions')
        for step in transitions+([row['pending']] if row.get('pending') is not None else []):
            if not isinstance(step,dict) or step.get('direction') not in ('undo','redo') or step.get('state') not in ('confirmed','attempting','needs_attention'):
                raise ValueError('Invalid material transition')
            validate_texture(step.get('source'));validate_texture(step.get('target'))
        recovery=row.get('recovery')
        if recovery is not None:
            if (not isinstance(recovery,dict) or recovery.get('state') not in ('attempting','confirmed','needs_attention')
                    or recovery.get('choice') not in ('source','target') or not finite_number(recovery.get('started_at'))):
                raise ValueError('Invalid material recovery receipt')
            validate_texture(recovery.get('registered_before'));validate_texture(recovery.get('desired'))
        return row

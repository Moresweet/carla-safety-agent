"""Write-ahead journal for managed actor texture edits, not undo authorization."""
import time
import uuid
import threading
from pathlib import Path
from .actor_materials import SUPPORTED
from .material_history import validate_texture, MaterialHistory
from .scene_store import atomic, identifier, read_json, finite_number


def validate_identity(identity):
    if not isinstance(identity,dict) or set(identity)!={'episode','actor_id','stable_id','blueprint_id','component','slot'}:
        raise ValueError('Exact managed actor identity required')
    identifier(identity['stable_id'])
    if (not isinstance(identity['episode'],str) or not identity['episode'].isascii()
            or not identity['episode'].isdigit() or type(identity['actor_id']) is not int
            or not 0<identity['actor_id']<2**32):raise ValueError('Invalid actor runtime identity')
    layout=SUPPORTED.get(identity['blueprint_id']) if isinstance(identity['blueprint_id'],str) else None
    if layout is None or type(identity['slot']) is not int or (identity['component'],identity['slot'])!=layout[:2]:
        raise ValueError('Unverified actor material slot')


class ActorMaterialHistory:
    def __init__(self,root):self.root=Path(root);self.lock=threading.RLock()

    # Same durable transition protocol, but actor-specific reader and verifier.
    transition=MaterialHistory.transition
    inspect=MaterialHistory.inspect
    recover=MaterialHistory.recover
    inspection_token=staticmethod(MaterialHistory.inspection_token)
    require_resolved_slot=MaterialHistory.require_resolved_slot

    def path(self,operation):
        identifier(operation)
        path=self.root/(operation+'.json')
        if self.root.is_symlink() or path.is_symlink():raise ValueError('Linked actor material journal')
        return path

    def read(self,operation):
        path=self.path(operation)
        row=read_json(path,max_bytes=64*1024)
        if (not isinstance(row,dict) or row.get('schema_version')!='carla-actor-material-history/1'
                or row.get('kind')!='actor-material' or row.get('operation_id')!=operation
                or row.get('state') not in ('attempting','confirmed','needs_attention')
                or row.get('undo_supported') is not False):raise ValueError('Invalid actor material journal')
        validate_identity(row.get('identity'))
        validate_texture(row.get('before'));validate_texture(row.get('after'))
        if not finite_number(row.get('created_at')) or row['created_at']<0:raise ValueError('Invalid actor material time')
        if type(row.get('applied',True)) is not bool:raise ValueError('Invalid actor material applied state')
        if 'revision' in row:identifier(row['revision'])
        transitions=row.get('transitions',[])
        if not isinstance(transitions,list) or len(transitions)>100:raise ValueError('Invalid actor material transitions')
        for step in transitions+([row['pending']] if row.get('pending') is not None else []):
            if not isinstance(step,dict) or step.get('direction') not in ('undo','redo') or step.get('state') not in ('attempting','confirmed','needs_attention'):
                raise ValueError('Invalid actor material transition')
            validate_texture(step.get('source'));validate_texture(step.get('target'))
        recovery=row.get('recovery')
        if recovery is not None:
            if (not isinstance(recovery,dict) or recovery.get('state') not in ('attempting','confirmed','needs_attention')
                    or recovery.get('choice') not in ('source','target') or not finite_number(recovery.get('started_at'))):
                raise ValueError('Invalid actor material recovery receipt')
            validate_texture(recovery.get('registered_before'));validate_texture(recovery.get('desired'))
        return row


def apply_with_history(root,identity,before,after,transaction):
    validate_identity(identity)
    validate_texture(before);validate_texture(after)
    root=Path(root)
    if root.is_symlink():raise ValueError('Linked actor material journal')
    # Production caller holds simulation_operation across snapshot and write.
    ActorMaterialHistory(root).require_resolved_slot(identity)
    root.mkdir(parents=True,exist_ok=True)
    operation=uuid.uuid4().hex
    path=root/(operation+'.json')
    row=dict(schema_version='carla-actor-material-history/1',kind='actor-material',
             operation_id=operation,identity=dict(identity),before=before,after=after,
             state='attempting',created_at=time.time(),undo_supported=False)
    atomic(path,row)
    try:
        transaction.apply()
    except Exception as error:
        row.update(state='needs_attention',error=str(error)[:2000])
        try:
            transaction.rollback()
            row['rollback']='returned'
        except Exception as recovery:
            row.update(rollback='failed',rollback_error=str(recovery)[:2000])
        atomic(path,row)
        raise RuntimeError(f'Actor material edit {operation} requires inspection: {error}') from error
    try:
        atomic(path,{**row,'state':'confirmed','finished_at':time.time()})
    except Exception as error:
        # The native edit may have succeeded; retain the write-ahead intent.
        raise RuntimeError(f'Actor material edit {operation} result uncertain: {error}') from error
    return operation

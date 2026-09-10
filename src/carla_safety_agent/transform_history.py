"""Per-runtime-actor move history with write-ahead intent and explicit inspection."""
import copy
import hashlib
import json
import threading
import time
import uuid
from pathlib import Path
from .scene_store import atomic,read_json,identifier,validate_transform_patch,finite_number
from .transform_review import validate_review

LIMIT=1000


def validate_pose(pose):
    validate_transform_patch(pose)
    if set(pose)!={'location','rotation'} or set(pose['location'])!={'x','y','z'} or set(pose['rotation'])!={'pitch','yaw','roll'}:
        raise ValueError('Complete move-history pose required')
    return pose


def same_pose(a,b):
    validate_pose(a);validate_pose(b)
    return all(abs(a['location'][k]-b['location'][k])<=.02 for k in ('x','y','z')) and all(abs((a['rotation'][k]-b['rotation'][k]+180)%360-180)<=.05 for k in ('pitch','yaw','roll'))


def validate_identity(identity):
    if not isinstance(identity,dict) or set(identity)!={'episode','actor_id','type_id','stable_id'}:
        raise ValueError('Invalid move-history actor identity')
    identifier(identity['stable_id'])
    validate_review({k:v for k,v in identity.items() if k!='stable_id'}|{'location':{'x':0,'y':0,'z':0},'yaw':0})
    return identity


class TransformHistory:
    def __init__(self,root):
        self.root=Path(root);self.lock=threading.RLock()

    def folder(self,identity):
        validate_identity(identity)
        key=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
        folder=self.root/key
        if self.root.is_symlink() or folder.is_symlink():raise ValueError('Linked move history refused')
        return folder

    def read(self,identity):
        with self.lock:
            path=self.folder(identity)/'current.json'
            if path.is_symlink():raise ValueError('Linked move history refused')
            try:row=read_json(path,max_bytes=4*1024**2)
            except FileNotFoundError:return {'schema_version':'carla-transform-history/1','identity':copy.deepcopy(identity),'revision':None,'entries':[],'cursor':0,'pending':None}
            if not isinstance(row,dict) or row.get('schema_version')!='carla-transform-history/1' or row.get('identity')!=identity:
                raise ValueError('Move history identity or schema mismatch')
            if set(row)!={'schema_version','identity','revision','entries','cursor','pending'}:
                raise ValueError('Unexpected or missing move history fields')
            identifier(row.get('revision'))
            entries=row.get('entries');cursor=row.get('cursor')
            if not isinstance(entries,list) or len(entries)>LIMIT or type(cursor) is not int or not 0<=cursor<=len(entries):
                raise ValueError('Invalid move history cursor or entries')
            seen=set()
            for entry in entries:
                self.validate_entry(entry)
                if entry['id'] in seen:raise ValueError('Duplicate move entry')
                seen.add(entry['id'])
            if any(not same_pose(a['after'],b['before']) for a,b in zip(entries,entries[1:])):
                raise ValueError('Position history chain is discontinuous')
            pending=row.get('pending')
            if pending is not None:
                if not isinstance(pending,dict) or pending.get('kind') not in ('record','undo','redo') or pending.get('state') not in ('attempting','needs_attention'):
                    raise ValueError('Invalid pending move intent')
                identifier(pending.get('id'));validate_pose(pending.get('source'));validate_pose(pending.get('target'))
                if pending['kind']=='record':
                    self.validate_entry(pending.get('entry'))
                    if pending['entry']['before']!=pending['source'] or pending['entry']['after']!=pending['target'] or pending['entry']['id'] in seen:
                        raise ValueError('Pending position record differs from intent')
                    if cursor!=len(entries) or len(entries)>=LIMIT or (entries and not same_pose(entries[-1]['after'],pending['source'])):
                        raise ValueError('Pending position record cannot extend this chain')
                elif not (cursor>0 if pending['kind']=='undo' else cursor<len(entries)):
                    raise ValueError('Pending history direction is invalid')
                else:
                    entry=entries[cursor-1 if pending['kind']=='undo' else cursor]
                    source,target=(entry['after'],entry['before']) if pending['kind']=='undo' else (entry['before'],entry['after'])
                    if not same_pose(source,pending['source']) or target!=pending['target']:
                        raise ValueError('Pending history target differs from selected entry')
            return row

    @staticmethod
    def validate_entry(entry):
        if not isinstance(entry,dict):raise ValueError('Invalid move entry')
        identifier(entry.get('id'));validate_pose(entry.get('before'));validate_pose(entry.get('after'))
        if not finite_number(entry.get('created_at')) or entry['created_at']<0:raise ValueError('Invalid move entry time')

    def write(self,identity,row):
        folder=self.folder(identity);folder.mkdir(parents=True,exist_ok=True)
        row['revision']=uuid.uuid4().hex
        atomic(folder/'current.json',row)
        return copy.deepcopy(row)

    def archive(self,identity,row):
        if row['revision'] is not None:
            path=self.folder(identity)/(row['revision']+'.json')
            if path.exists() or path.is_symlink():
                if path.is_symlink() or read_json(path,max_bytes=4*1024**2)!=row:raise ValueError('Existing position archive differs; preserve for inspection')
            else:atomic(path,row)

    def begin(self,identity,kind,current,target=None,expected_revision=None):
        with self.lock:
            row=self.read(identity)
            if row['pending'] is not None:raise ValueError('Previous position edit needs inspection before further history operations')
            validate_pose(current)
            if kind=='record':
                validate_pose(target)
                if current==target:raise ValueError('Position is unchanged; no history entry needed')
                # Never join an externally moved pose onto a fictitious chain.
                external=row['cursor']>0 and not same_pose(row['entries'][row['cursor']-1]['after'],current)
                if external or row['cursor']<len(row['entries']):
                    self.archive(identity,row)
                    row['entries']=[] if external else row['entries'][:row['cursor']]
                    row['cursor']=len(row['entries'])
                if len(row['entries'])>=LIMIT:raise ValueError('Position history limit reached; retain and inspect archive')
                entry={'id':uuid.uuid4().hex,'before':copy.deepcopy(current),'after':copy.deepcopy(target),'created_at':time.time()}
            else:
                if kind not in ('undo','redo') or expected_revision!=row['revision']:raise ValueError('History changed; refresh before undo or redo')
                index=row['cursor']-1 if kind=='undo' else row['cursor']
                if not 0<=index<len(row['entries']):raise ValueError('No earlier/later position edit')
                entry=row['entries'][index]
                source=entry['after'] if kind=='undo' else entry['before']
                if not same_pose(current,source):raise ValueError('Object moved outside this history; refusing to overwrite its current pose')
                target=entry['before'] if kind=='undo' else entry['after']
            row['pending']={'id':uuid.uuid4().hex,'kind':kind,'state':'attempting','source':copy.deepcopy(current),'target':copy.deepcopy(target),**({'entry':entry} if kind=='record' else {})}
            return self.write(identity,row)

    def finish(self,identity,intent_id,observed):
        with self.lock:
            row=self.read(identity);pending=row['pending']
            if not pending or pending['id']!=intent_id or pending['state']!='attempting':raise ValueError('Move intent identity changed or needs inspection')
            if not same_pose(observed,pending['target']):raise ValueError('Native position did not settle at the requested pose; inspect before retrying')
            if pending['kind']=='record':row['entries'].append(pending['entry']);row['cursor']+=1
            else:row['cursor']+=-1 if pending['kind']=='undo' else 1
            row['pending']=None
            return self.write(identity,row)

    def fail(self,identity,intent_id,error):
        with self.lock:
            row=self.read(identity)
            if not row['pending'] or row['pending']['id']!=intent_id:raise ValueError('Move intent no longer pending; inspect durable history')
            row['pending'].update(state='needs_attention',error=str(error)[:2000])
            return self.write(identity,row)

    def acknowledge(self,identity,revision,intent_id,confirmed):
        with self.lock:
            row=self.read(identity)
            if confirmed is not True or row['revision']!=revision or not row['pending'] or row['pending']['id']!=intent_id:
                raise ValueError('Explicit inspection of the current pending position edit required')
            self.archive(identity,row)
            # The world may have moved: do not advertise an old chain as valid.
            row.update(entries=[],cursor=0,pending=None)
            return self.write(identity,row)

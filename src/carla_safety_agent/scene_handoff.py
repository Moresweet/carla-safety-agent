"""Persistent fail-closed gate for explicitly reviewed, destructive map handoffs."""
from contextlib import contextmanager
from pathlib import Path
import threading
import time
import uuid

from .bundle_restore_review import baseline_digest,digest
from .scene_store import atomic,identifier,read_json,finite_number

PENDING={'running','needs_attention'}
STATES=PENDING|{'restored','failed_before_switch','acknowledged'}


def available_map(requested,available):
    from .world_readiness import map_matches
    # Some native builds enumerate short names, while saved worlds use package
    # paths. Keep exact basename matching, never Town05-prefix matching.
    candidates=[name for name in available if map_matches(requested,name) or
        ('/' not in name.strip('/') and map_matches(name,requested))]
    if len(candidates)!=1:raise ValueError('Target map is unavailable or ambiguous')
    return candidates[0]


def validate_journal(row):
    if (not isinstance(row,dict) or row.get('schema_version')!='carla-scene-handoff/1'
        or row.get('state') not in STATES or row.get('phase') not in ('prepared','loading_map','restoring_scene','verified')):
        raise ValueError('Invalid map handoff journal')
    identifier(row.get('request_id'))
    selection=row.get('selection');backup=row.get('backup')
    if not isinstance(selection,dict) or set(selection)!={'scene_id','version'} or not isinstance(backup,dict):
        raise ValueError('Invalid map handoff selection or backup')
    for record in (selection,backup):
        identifier(record.get('scene_id'));identifier(record.get('version'))
    for key in ('source_map','target_map'):
        if not isinstance(row.get(key),str) or not 1<=len(row[key])<=256:raise ValueError('Invalid map handoff map')
    episode=row.get('source_episode')
    if not isinstance(episode,str) or not episode.isascii() or not episode.isdigit() or not 0<=int(episode)<2**64:
        raise ValueError('Invalid map handoff source episode')
    for key in ('started_at','updated_at'):
        if key in row and (not finite_number(row[key]) or row[key]<0):raise ValueError('Invalid map handoff time')
    if 'started_at' not in row:raise ValueError('Missing map handoff start time')
    return row


class SceneHandoff:
    def __init__(self,root,clock=time.monotonic):
        self.root=Path(root);self.path=self.root/'current.json'
        self.lock=threading.RLock();self.local=threading.local();self.worker_active=False
        self.clock=clock;self.reviews={}

    def status(self):
        with self.lock:
            if self.root.is_symlink() or self.path.is_symlink():raise ValueError('Linked handoff journal refused')
            try:row=read_json(self.path,max_bytes=2*1024**2)
            except FileNotFoundError:return {'state':'idle'}
            validate_journal(row)
            if row['state']=='running' and not self.worker_active:
                row={**row,'state':'needs_attention','error':'Bridge interrupted during map handoff; inspect current world and backup before acknowledging; no automatic retry'}
            return row

    def require_idle(self):
        if getattr(self.local,'owner',False):return
        if self.status()['state'] in PENDING:
            raise ValueError('Map handoff is running or needs inspection; ordinary world operations are blocked')

    @contextmanager
    def owner_scope(self):
        previous=getattr(self.local,'owner',False);self.local.owner=True
        try:yield
        finally:self.local.owner=previous

    def preview(self,selection,document,baseline,episode,actor_inventory):
        self.require_idle()
        if document['map']==baseline['map']:raise ValueError('Use same-map scene restore for this selection')
        now=self.clock()
        self.reviews={k:v for k,v in self.reviews.items() if v['expires']>now}
        if len(self.reviews)>=64:raise ValueError('Too many map handoff reviews; wait for expiry')
        token=uuid.uuid4().hex
        self.reviews[token]={'selection':dict(selection),'target_digest':digest(document),
            'baseline_digest':baseline_digest(baseline),'episode':str(episode),
            'inventory_digest':digest(actor_inventory),'expires':now+120}
        return {'review_token':token,'expires_in_s':120,'selection':selection,'source_map':baseline['map'],
            'target_map':document['map'],'source_episode':str(episode),'target_object_count':len(document['objects']),
            'saved_user_object_count':len(baseline['objects']),'world_modified':False,
            'warning':'Map loading destroys the current runtime world. Managed state is backed up, not a complete simulator snapshot. Failure needs inspection; no automatic map rollback.'}

    def selection(self,token):
        if not isinstance(token,str) or token not in self.reviews:raise ValueError('Unknown or consumed map review')
        row=self.reviews[token]
        if row['expires']<=self.clock():self.reviews.pop(token);raise ValueError('Map review expired')
        return dict(row['selection'])

    def consume(self,data,document,baseline,episode,inventory):
        if not isinstance(data,dict) or set(data)!={'review_token','confirmed'} or data['confirmed'] is not True:
            raise ValueError('Explicit destructive map handoff confirmation required')
        selection=self.selection(data['review_token']);row=self.reviews.pop(data['review_token'])
        if (row['target_digest']!=digest(document) or row['baseline_digest']!=baseline_digest(baseline)
            or row['episode']!=str(episode) or row['inventory_digest']!=digest(inventory)):
            raise ValueError('Scene or world changed since map review; preview again')
        return selection

    def begin(self,review,backup):
        with self.lock:
            self.require_idle();previous=self.status()
            self.root.mkdir(parents=True,exist_ok=True)
            if previous['state']!='idle':atomic(self.root/(previous['request_id']+'.json'),previous)
            row={'schema_version':'carla-scene-handoff/1','request_id':uuid.uuid4().hex,'state':'running',
                'phase':'prepared','selection':review['selection'],'source_episode':review['source_episode'],
                'source_map':review['source_map'],'target_map':review['target_map'],'backup':backup,
                'started_at':time.time(),'error':None}
            atomic(self.path,validate_journal(row));self.worker_active=True
            return row

    def update(self,request_id,**fields):
        with self.lock:
            row=self.status()
            if row.get('request_id')!=request_id:raise ValueError('Map handoff identity changed')
            if fields.get('state',row['state']) not in STATES:raise ValueError('Invalid handoff state')
            row={**row,**fields,'updated_at':time.time()};atomic(self.path,validate_journal(row));return row

    def acknowledge(self,data):
        with self.lock:
            if not isinstance(data,dict) or set(data)!={'request_id','confirmed'} or data['confirmed'] is not True:
                raise ValueError('Explicit acknowledgement of the current world required')
            row=self.status()
            if self.worker_active or row['state']!='needs_attention' or row.get('request_id')!=data['request_id']:
                raise ValueError('Only an inactive interrupted handoff can be acknowledged')
            return self.update(data['request_id'],state='acknowledged',
                note='User accepted the inspected current world; this does not certify that the target scene was restored')

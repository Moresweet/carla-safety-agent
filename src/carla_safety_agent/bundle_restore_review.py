"""Single-use, short-lived consent bound to a package and managed world snapshot."""
import hashlib
import json
import time
import uuid


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,allow_nan=False,separators=(',',':')).encode()).hexdigest()


def baseline_digest(document):
    value=dict(document)
    for key in ('objects','environment_materials','hidden_environment','actor_materials'):
        if key in value:value[key]=sorted(value[key],key=digest)
    return digest(value)


class RestoreReviews:
    """Caller serializes issue/consume with the bridge simulation-operation lock."""
    def __init__(self,clock=time.monotonic):
        self.clock=clock
        self.pending={}

    def issue(self,selection,manifest,document,baseline,episode):
        if document['map']!=baseline['map']:
            raise ValueError('Scene belongs to another map; this workflow never switches maps')
        now=self.clock()
        self.pending={key:value for key,value in self.pending.items() if value['expires']>now}
        if len(self.pending)>=64:raise ValueError('Too many pending restore reviews; wait for expiry')
        token=uuid.uuid4().hex
        self.pending[token]={'selection':dict(selection),'manifest':digest(manifest),
            'baseline':baseline_digest(baseline),'episode':str(episode),'expires':now+120}
        live={obj['stable_id']:obj for obj in baseline['objects']}
        updates=sum(obj['stable_id'] in live for obj in document['objects'])
        return {'ok':True,'review_token':token,'expires_in_s':120,'selection':selection,
            'map':document['map'],'episode':str(episode),'create_count':len(document['objects'])-updates,
            'update_count':updates,'preserved_user_objects':len(set(live)-{obj['stable_id'] for obj in document['objects']}),
            'weather_fields':sorted(document.get('weather',{})),
            'camera_changed':'spectator' in document,
            'material_state_replaced':'environment_materials' in document,
            'actor_material_state_replaced':'actor_materials' in document,
            'actor_material_count':len(document.get('actor_materials',[])),
            'visibility_state_replaced':'hidden_environment' in document,
            'live_world_modified':False,'dependency_preflight_completed':False}

    def selection(self,token):
        if not isinstance(token,str) or token not in self.pending:
            raise ValueError('Unknown or already used restore review; preview again')
        row=self.pending[token]
        if row['expires']<=self.clock():
            self.pending.pop(token)
            raise ValueError('Restore review expired; preview again')
        return dict(row['selection'])

    def consume(self,data,manifest,baseline,episode):
        if not isinstance(data,dict) or set(data)!={'review_token','confirmed'} or data['confirmed'] is not True:
            raise ValueError('Restore requires explicit confirmation of a review token')
        token=data['review_token']
        selection=self.selection(token)
        row=self.pending.pop(token)  # Never retry mutation with the same approval, even after an error.
        if row['episode']!=str(episode):raise ValueError('World changed since preview; preview again')
        if row['manifest']!=digest(manifest):raise ValueError('Package changed since preview; preview again')
        if row['baseline']!=baseline_digest(baseline):raise ValueError('Managed scene changed since preview; preview again')
        return selection

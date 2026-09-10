"""Episode-scoped actor provenance shared by editor and evaluator processes."""
import fcntl
import json
import os
import re
import uuid
from pathlib import Path


def _invalid_constant(value):
    raise ValueError('Non-finite JSON value: '+value)


def _unique_mapping(pairs):
    result={}
    for key,value in pairs:
        if key in result:
            raise ValueError('Duplicate provenance key: '+key)
        result[key]=value
    return result


class ActorProvenance:
    def __init__(self, path):
        self.path = Path(path)

    def records(self, episode):
        return self._read().get(self._episode(episode), {})

    @staticmethod
    def _episode(episode):
        if type(episode) is not int or not 0 <= episode < 2**64:
            raise ValueError('Invalid provenance episode')
        return str(episode)

    @staticmethod
    def _actor(actor):
        if (type(actor.id) is not int or actor.id <= 0 or
                not isinstance(actor.type_id,str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,200}',actor.type_id)):
            raise ValueError('Invalid provenance actor identity')
        return str(actor.id)

    def _read(self):
        try:
            with self.path.open() as stream:
                raw=stream.read(16*1024*1024+1)
        except FileNotFoundError:
            return {}
        if len(raw)>16*1024*1024:
            raise ValueError('Oversized actor provenance; original file preserved')
        try:
            data=json.loads(raw,parse_constant=_invalid_constant,object_pairs_hook=_unique_mapping)
            if not isinstance(data,dict): raise ValueError('Expected episode mapping')
            for episode,records in data.items():
                if not episode.isascii() or not episode.isdigit() or str(int(episode))!=episode or not 0<=int(episode)<2**64:
                    raise ValueError('Invalid stored episode')
                if not isinstance(records,dict): raise ValueError('Invalid actor mapping')
                for actor_id,item in records.items():
                    if not actor_id.isascii() or not actor_id.isdigit() or str(int(actor_id))!=actor_id or int(actor_id)<=0:
                        raise ValueError('Invalid stored actor ID')
                    if (not isinstance(item,dict) or item.get('origin') not in ('existing','user','evaluation','unknown') or
                            not isinstance(item.get('type_id'),str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,200}',item['type_id'])):
                        raise ValueError('Invalid stored actor identity')
                    if 'stable_id' in item and (not isinstance(item['stable_id'],str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,200}',item['stable_id'])):
                        raise ValueError('Invalid stored stable ID')
            return data
        except (ValueError,TypeError) as exc:
            raise ValueError(f'Actor provenance unreadable; original file preserved: {self.path}: {exc}') from exc

    def _write(self,data):
        payload=json.dumps(data,allow_nan=False)
        temporary=self.path.with_name(self.path.name+'.'+uuid.uuid4().hex+'.tmp')
        with temporary.open('x') as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(self.path)
        descriptor=os.open(self.path.parent,os.O_RDONLY|os.O_DIRECTORY)
        try: os.fsync(descriptor)
        finally: os.close(descriptor)

    def origin(self, episode, actor, default='unknown'):
        item = self.records(episode).get(str(actor.id), {})
        return item.get('origin', default) if item.get('type_id') == actor.type_id else default

    def mark(self, episode, actors, origin, overwrite=True):
        episode=self._episode(episode)
        actors=list(actors)
        for actor in actors: self._actor(actor)
        if origin not in ('existing','user','evaluation','unknown'):
            raise ValueError('Invalid actor origin')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.with_suffix('.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            data = self._read()
            records = data.setdefault(episode, {})
            for actor in actors:
                previous = records.get(str(actor.id), {})
                same_type = previous.get('type_id') == actor.type_id
                if overwrite or not same_type:
                    records[str(actor.id)] = {**(previous if same_type else {}),
                        'type_id': actor.type_id, 'origin': origin,
                        'stable_id': previous.get('stable_id', uuid.uuid4().hex) if same_type else uuid.uuid4().hex}
                records[str(actor.id)].setdefault('stable_id', uuid.uuid4().hex)
            self._write(data)

    def bind(self, episode, actor, stable_id, **metadata):
        """Persist logical identity and spawn metadata after a successful restore."""
        episode=self._episode(episode)
        actor_id=self._actor(actor)
        if not isinstance(stable_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,200}',stable_id):
            raise ValueError('Invalid stable ID')
        if {'origin','type_id','stable_id'}.intersection(metadata):
            raise ValueError('Metadata cannot replace actor identity')
        json.dumps(metadata,allow_nan=False)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.path.with_suffix('.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            data = self._read()
            records=data.setdefault(episode,{})
            previous=records.get(actor_id,{})
            item=previous if previous.get('type_id')==actor.type_id else {'type_id':actor.type_id,'origin':'user'}
            records[actor_id]={**item,'stable_id':stable_id,**metadata}
            self._write(data)

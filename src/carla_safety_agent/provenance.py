"""Episode-scoped actor provenance shared by editor and evaluator processes."""
import fcntl
import json
import uuid
from pathlib import Path


class ActorProvenance:
    def __init__(self, path):
        self.path = Path(path)

    def records(self, episode):
        try:
            return json.loads(self.path.read_text()).get(str(episode), {})
        except (OSError, ValueError):
            return {}

    def origin(self, episode, actor, default='existing'):
        item = self.records(episode).get(str(actor.id), {})
        return item.get('origin', default) if item.get('type_id') == actor.type_id else default

    def mark(self, episode, actors, origin, overwrite=True):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.with_suffix('.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                data = json.loads(self.path.read_text())
            except (OSError, ValueError):
                data = {}
            records = data.setdefault(str(episode), {})
            for actor in actors:
                previous = records.get(str(actor.id), {})
                if overwrite or str(actor.id) not in records:
                    records[str(actor.id)] = {'type_id': actor.type_id, 'origin': origin,
                        'stable_id': previous.get('stable_id', uuid.uuid4().hex)}
                records[str(actor.id)].setdefault('stable_id', uuid.uuid4().hex)
            temporary = self.path.with_suffix('.tmp')
            temporary.write_text(json.dumps(data))
            temporary.replace(self.path)

    def bind(self, episode, actor, stable_id, **metadata):
        """Persist logical identity and spawn metadata after a successful restore."""
        self.mark(episode, [actor], 'user', overwrite=False)
        with self.path.with_suffix('.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            data = json.loads(self.path.read_text())
            data[str(episode)][str(actor.id)].update(stable_id=stable_id, **metadata)
            temporary = self.path.with_suffix('.tmp')
            temporary.write_text(json.dumps(data))
            temporary.replace(self.path)

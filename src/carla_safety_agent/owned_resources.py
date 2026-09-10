"""Durable native-worker actor identities; recovery never deletes by category."""
import json
import os
from pathlib import Path
import re
import uuid

from .scene_store import identifier
from .session import observed_process_identity

SCHEMA = 'carla-owned-resources/2'


def resource_path(root, run_id):
    run_id = identifier(run_id)
    base = Path(root).resolve()
    path = (base/'experiments'/run_id/'owned-resources.json').resolve()
    if base not in path.parents:
        raise ValueError('Resource journal outside project data')
    return path


def durable_write(path, document, *, exclusive=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path if exclusive else path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    with temporary.open('x') as stream:
        json.dump(document, stream, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())
    if not exclusive:
        temporary.replace(path)
    descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class OwnedResourceJournal:
    def __init__(self, root, run_id, world, owner):
        if not owner:
            raise ValueError('Resource journal requires a live worker identity')
        self.path = resource_path(root, run_id)
        self.document = {'schema_version': SCHEMA, 'run_id': run_id, 'owner': owner,
                         'episode': world.id, 'map': world.get_map().name,
                         'state': 'active', 'actors': [],
                         'baseline_actor_ids': sorted(actor.id for actor in world.get_actors())}
        if len(self.document['baseline_actor_ids']) > 10000:
            raise ValueError('World actor baseline exceeds journal limit')
        durable_write(self.path, self.document, exclusive=True)

    def register(self, actor):
        entry = {'id': actor.id, 'type_id': actor.type_id}
        previous = next((row for row in self.document['actors'] if row['id'] == actor.id), None)
        if previous is not None:
            if previous != entry:
                raise ValueError('Owned actor identity changed')
            return
        if len(self.document['actors']) >= 10000:
            raise ValueError('Owned actor journal limit exceeded')
        self.document['actors'].append(entry)
        durable_write(self.path, self.document)


class OwnedActors(list):
    def __init__(self, journal=None):
        super().__init__()
        self.journal = journal

    def append(self, actor):
        # Retain the in-process handle even if the durable write fails.
        super().append(actor)
        if self.journal:
            self.journal.register(actor)

    def extend(self, actors):
        actors = list(actors)
        super().extend(actors)
        if self.journal:
            for actor in actors:
                self.journal.register(actor)

    def __iadd__(self, actors):
        self.extend(actors)
        return self


def journal_from_environment(world):
    root = os.environ.get('CSA_RESOURCE_DATA_ROOT')
    run_id = os.environ.get('CSA_EXECUTION_ID')
    if root is None:
        return None
    if not run_id:
        raise ValueError('Missing resource execution identity')
    return OwnedResourceJournal(root, run_id, world, observed_process_identity(os.getpid()))


def read_resources(path, session):
    if path.stat().st_size > 2*1024*1024:
        raise ValueError('Oversized resource journal')
    document = json.loads(path.read_text())
    if (not isinstance(document, dict) or document.get('schema_version') not in (SCHEMA, 'carla-owned-resources/1') or
            document.get('run_id') != session['run_id'] or
            not isinstance(document.get('owner'), dict) or
            document['owner'] != session.get('process') or
            document.get('state') not in ('active', 'recovered') or
            type(document.get('episode')) is not int or
            not isinstance(document.get('map'), str) or
            not isinstance(document.get('actors'), list) or len(document['actors']) > 10000):
        raise ValueError('Resource journal identity mismatch')
    ids = set()
    baseline = document.get('baseline_actor_ids')
    if document['schema_version'] == SCHEMA and not isinstance(baseline, list):
        raise ValueError('Missing world actor baseline')
    if baseline is not None and (not isinstance(baseline, list) or len(baseline) > 10000 or
            any(type(actor_id) is not int or actor_id <= 0 for actor_id in baseline) or
            len(set(baseline)) != len(baseline)):
        raise ValueError('Invalid world actor baseline')
    owner = document['owner']
    if (set(owner) != {'pid', 'start_ticks'} or type(owner['pid']) is not int or owner['pid'] <= 0 or
            not isinstance(owner['start_ticks'], str) or not owner['start_ticks'].isdigit()):
        raise ValueError('Invalid resource process identity')
    for row in document['actors']:
        if (not isinstance(row, dict) or set(row) != {'id', 'type_id'} or
                type(row['id']) is not int or row['id'] <= 0 or row['id'] in ids or
                not isinstance(row['type_id'], str) or
                not re.fullmatch(r'[A-Za-z0-9_.-]{1,200}', row['type_id'])):
            raise ValueError('Invalid owned actor identity')
        ids.add(row['id'])
    return document


def recover_owned_resources(root, session, client, carla, *, observe=observed_process_identity):
    if session.get('state') != 'recovering':
        raise ValueError('Owned resources require a recovering session')
    path = resource_path(root, session['run_id'])
    if not path.exists():
        return None  # Legacy/non-native worker: no invented ownership.
    document = read_resources(path, session)
    owner = document['owner']
    if observe(owner['pid']) == owner:
        raise RuntimeError('Resource owner is still alive')
    world = client.get_world()
    if world.id != document['episode'] or world.get_map().name != document['map']:
        return {'state': 'different_world', 'mutated': False}
    rows = document['actors']
    ids = {row['id'] for row in rows}
    current_actors = world.get_actors()
    if document['schema_version'] == 'carla-owned-resources/1':
        # Compatibility with the first development format is observation-only.
        # Never manufacture a pre-run baseline from the post-run world.
        if (session.get('returncode') != 0 or world.get_settings().synchronous_mode or
                list(current_actors.filter('sensor.*')) or
                ids.intersection(actor.id for actor in current_actors)):
            raise RuntimeError('Legacy resource journal requires manual recovery review')
        document['state'] = 'recovered'
        durable_write(path, document)
        return {'state': 'legacy_clean_observed', 'mutated': False,
                'scope': 'Known actors absent after successful worker exit; no baseline verification'}
    if any(actor.id not in ids for actor in current_actors.filter('sensor.*')):
        raise RuntimeError('Unowned sensors present; refusing resource recovery')
    unknown = {actor.id for actor in current_actors} - ids - set(document['baseline_actor_ids'])
    if unknown:
        raise RuntimeError(f'Unjournaled new actors require review: {sorted(unknown)}')
    if document['state'] == 'recovered':
        return {'state': 'recovered', 'mutated': False}
    expected = {row['id']: row['type_id'] for row in rows}
    # Explicit lookup also sees a registered actor before its first physics snapshot.
    for actor in world.get_actors(list(ids)):
        if actor.id not in expected or actor.type_id != expected[actor.id]:
            raise RuntimeError('Owned actor type changed; refusing all mutations')
    ordered = sorted(rows, key=lambda row: not row['type_id'].startswith('sensor.'))
    if ordered:
        responses = client.apply_batch_sync([carla.command.DestroyActor(row['id']) for row in ordered], False)
        if len(responses) != len(ordered):
            raise RuntimeError('Incomplete resource recovery acknowledgement')
        errors = [f"{row['id']}: {response.error}" for row, response in zip(ordered, responses)
                  if response.error and response.error != 'unable to destroy actor: not found']
        if errors:
            raise RuntimeError('Resource recovery incomplete: '+'; '.join(errors))
    document['state'] = 'recovered'
    durable_write(path, document)
    return {'state': 'recovered', 'owned_actor_ids': sorted(ids), 'mutated': bool(rows)}

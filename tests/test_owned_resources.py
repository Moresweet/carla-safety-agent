import json
from types import SimpleNamespace as NS

import pytest

from carla_safety_agent.owned_resources import OwnedActors, OwnedResourceJournal, recover_owned_resources

RUN = 'a'*32
OWNER = {'pid': 123, 'start_ticks': '456'}


def setup(tmp_path):
    calls = []
    world = NS(id=7, get_map=lambda: NS(name='Town04'), get_actors=lambda: [])
    journal = OwnedResourceJournal(tmp_path, RUN, world, OWNER)
    actors = [NS(id=10, type_id='vehicle.test'), NS(id=11, type_id='sensor.camera.rgb')]
    OwnedActors(journal).extend(actors)
    class ActorList(list):
        def filter(self, pattern):
            return [actor for actor in self if actor.type_id.startswith('sensor.')]
    world.get_actors = lambda ids=None: actors if ids is not None else ActorList(actors)
    client = NS(get_world=lambda: world,
                apply_batch_sync=lambda ids, tick: calls.append((ids, tick)) or [NS(error='') for _ in ids])
    carla = NS(command=NS(DestroyActor=lambda actor_id: actor_id))
    session = {'state': 'recovering', 'run_id': RUN, 'process': OWNER}
    return journal, world, actors, client, carla, session, calls


def test_exact_ids_sensor_first_no_tick_and_idempotent(tmp_path):
    journal, world, actors, client, carla, session, calls = setup(tmp_path)
    result = recover_owned_resources(tmp_path, session, client, carla, observe=lambda _: None)
    assert result['owned_actor_ids'] == [10, 11] and calls == [([11, 10], False)]
    assert json.loads(journal.path.read_text())['state'] == 'recovered'
    assert not recover_owned_resources(tmp_path, session, client, carla, observe=lambda _: None)['mutated']
    assert len(calls) == 1


@pytest.mark.parametrize('failure', ['live', 'type', 'foreign_sensor', 'foreign_vehicle', 'identity', 'corrupt'])
def test_unverified_ownership_refuses_before_rpc(tmp_path, failure):
    journal, world, actors, client, carla, session, calls = setup(tmp_path)
    observe = lambda _: None
    if failure == 'live': observe = lambda _: OWNER
    if failure == 'type': actors[0].type_id = 'vehicle.other'
    if failure == 'foreign_sensor':
        world.get_actors = lambda ids=None: NS(filter=lambda _: [NS(id=99)])
    if failure == 'foreign_vehicle': actors.append(NS(id=99, type_id='vehicle.other'))
    if failure == 'identity': session['process'] = {'pid': 321, 'start_ticks': '456'}
    if failure == 'corrupt': journal.path.write_text('{}')
    with pytest.raises((ValueError, RuntimeError)):
        recover_owned_resources(tmp_path, session, client, carla, observe=observe)
    assert not calls


def test_another_episode_is_never_modified(tmp_path):
    journal, world, actors, client, carla, session, calls = setup(tmp_path)
    world.id = 8
    assert recover_owned_resources(tmp_path, session, client, carla, observe=lambda _: None) == {
        'state': 'different_world', 'mutated': False}
    assert calls == []


@pytest.mark.parametrize('errors', [[], ['internal error: unable to destroy actor', '']])
def test_missing_or_failed_ack_retains_active_journal(tmp_path, errors):
    journal, world, actors, client, carla, session, calls = setup(tmp_path)
    client.apply_batch_sync = lambda *args: [NS(error=error) for error in errors]
    with pytest.raises(RuntimeError):
        recover_owned_resources(tmp_path, session, client, carla, observe=lambda _: None)
    assert json.loads(journal.path.read_text())['state'] == 'active'


def test_known_absent_actor_response_is_idempotent_not_arbitrary_error(tmp_path):
    journal, world, actors, client, carla, session, calls = setup(tmp_path)
    client.apply_batch_sync = lambda *args: [NS(error='unable to destroy actor: not found'), NS(error='')]
    assert recover_owned_resources(tmp_path, session, client, carla, observe=lambda _: None)['state'] == 'recovered'


def test_failed_journaling_keeps_all_already_spawned_handles():
    def fail(actor): raise OSError('disk full')
    owned = OwnedActors(NS(register=fail))
    actors = [object(), object()]
    with pytest.raises(OSError): owned.extend(actors)
    assert owned == actors


def test_existing_journal_never_overwritten(tmp_path):
    journal, world, actors, client, carla, session, calls = setup(tmp_path)
    original = journal.path.read_bytes()
    with pytest.raises(FileExistsError): OwnedResourceJournal(tmp_path, RUN, world, OWNER)
    assert journal.path.read_bytes() == original


@pytest.mark.parametrize('unsafe', [None, 'alive_actor', 'synchronous', 'failed_worker'])
def test_legacy_format_only_observes_successful_clean_exit(tmp_path, unsafe):
    journal, world, actors, client, carla, session, calls = setup(tmp_path)
    document = json.loads(journal.path.read_text())
    document['schema_version'] = 'carla-owned-resources/1'
    document.pop('baseline_actor_ids')
    journal.path.write_text(json.dumps(document))
    session['returncode'] = 1 if unsafe == 'failed_worker' else 0
    world.get_settings = lambda: NS(synchronous_mode=unsafe == 'synchronous')
    if unsafe != 'alive_actor': actors.clear()
    if unsafe:
        with pytest.raises(RuntimeError, match='Legacy'):
            recover_owned_resources(tmp_path, session, client, carla, observe=lambda _: None)
    else:
        assert recover_owned_resources(tmp_path, session, client, carla, observe=lambda _: None)['state'] == 'legacy_clean_observed'
    assert not calls

from types import SimpleNamespace
import json
import pytest
from carla_safety_agent.provenance import ActorProvenance


def test_unobserved_origin_is_unknown_and_reconnect_preserves_known_origin(tmp_path):
    store = ActorProvenance(tmp_path/'actors.json')
    actor = SimpleNamespace(id=3, type_id='vehicle.test')
    assert store.origin(1, actor) == 'unknown'
    for origin in ('existing', 'user', 'evaluation', 'unknown'):
        store.mark(1, [actor], origin)
        store.mark(1, [actor], 'unknown', overwrite=False)
        assert store.origin(1, actor) == origin
        assert store.origin(2, actor) == 'unknown'
        assert store.origin(1, SimpleNamespace(id=3, type_id='vehicle.other')) == 'unknown'


def test_reclassification_preserves_generated_asset_metadata(tmp_path):
    store = ActorProvenance(tmp_path/'provenance.json')
    actor = SimpleNamespace(id=3,type_id='static.prop.mesh')
    store.bind(1,actor,'stable',blueprint_id='generated.asset',spawn_options={'scale':100})
    store.mark(1,[actor],'evaluation')
    record = store.records(1)['3']
    assert record['blueprint_id'] == 'generated.asset'
    assert record['spawn_options'] == {'scale':100}
    assert record['stable_id'] == 'stable'


def test_actor_id_reused_for_different_type_gets_new_identity(tmp_path):
    store = ActorProvenance(tmp_path/'provenance.json')
    store.bind(1,SimpleNamespace(id=3,type_id='static.prop.mesh'),'old',blueprint_id='generated.asset')
    store.mark(1,[SimpleNamespace(id=3,type_id='vehicle.test')],'evaluation',overwrite=False)
    record = store.records(1)['3']
    assert record['stable_id'] != 'old' and 'blueprint_id' not in record
    assert record['type_id'] == 'vehicle.test'


@pytest.mark.parametrize('raw',['{','[]','{"1": []}','{"1":{},"1":{}}',
    '{"1":{"2":{"type_id":"vehicle.test","origin":"invented"}}}',
    '{"1":{"2":{"type_id":"vehicle.test","origin":"user","stable_id":"../bad"}}}',
    '{"1":{"2":{"type_id":"vehicle.test","origin":"user","mass":NaN}}}'])
def test_corrupt_provenance_is_not_silently_overwritten(tmp_path,raw):
    path=tmp_path/'actors.json';path.write_text(raw)
    store=ActorProvenance(path);actor=SimpleNamespace(id=2,type_id='vehicle.test')
    for operation in (lambda:store.records(1),lambda:store.mark(1,[actor],'user'),
                      lambda:store.bind(1,actor,'stable')):
        with pytest.raises(ValueError): operation()
        assert path.read_text()==raw


def test_bind_is_one_atomic_update_and_preserves_origin(tmp_path,monkeypatch):
    store=ActorProvenance(tmp_path/'actors.json');actor=SimpleNamespace(id=2,type_id='vehicle.test')
    store.mark(1,[actor],'evaluation')
    writes=[];original=store._write
    def write(data): writes.append(data);original(data)
    monkeypatch.setattr(store,'_write',write)
    store.bind(1,actor,'stable',blueprint_id='vehicle.test')
    assert len(writes)==1 and store.records(1)['2']['origin']=='evaluation'


def test_invalid_binding_does_not_create_partial_user_record(tmp_path):
    store=ActorProvenance(tmp_path/'actors.json');actor=SimpleNamespace(id=2,type_id='vehicle.test')
    with pytest.raises(ValueError): store.bind(1,actor,'stable',spawn_options={'mass':float('nan')})
    with pytest.raises(ValueError): store.bind(1,actor,'stable',type_id='vehicle.other')
    assert not store.path.exists()


def test_provenance_write_failure_keeps_previous_document(tmp_path,monkeypatch):
    store=ActorProvenance(tmp_path/'actors.json');actor=SimpleNamespace(id=2,type_id='vehicle.test')
    store.mark(1,[actor],'user');before=store.path.read_bytes()
    def fail(_): raise OSError('disk full')
    monkeypatch.setattr('carla_safety_agent.provenance.os.fsync',fail)
    with pytest.raises(OSError): store.bind(1,actor,'new')
    assert store.path.read_bytes()==before


def test_large_uint64_episode_keeps_exact_identity(tmp_path):
    store=ActorProvenance(tmp_path/'actors.json');episode=10037400898563414813
    store.mark(episode,[SimpleNamespace(id=2,type_id='vehicle.test')],'user')
    assert str(episode) in json.loads(store.path.read_text())
    assert store.records(episode+1)=={}
    with pytest.raises(ValueError): store.records(float(episode))

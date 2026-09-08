from types import SimpleNamespace
from carla_safety_agent.provenance import ActorProvenance


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

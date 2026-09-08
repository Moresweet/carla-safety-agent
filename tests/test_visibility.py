import pytest
from carla_safety_agent.visibility import VisibilityStore, VisibilityTransaction, hidden_records


def record(number):
    return {'object_id':str(number), 'name':'object'+str(number)}


def test_visibility_survives_bridge_restart_not_world_change(tmp_path):
    store = VisibilityStore(tmp_path)
    store.record(1, 2, 'object2', False)
    assert VisibilityStore(tmp_path).records(1) == [record(2)]
    assert store.records(2) == []
    store.record(1, 2, 'object2', True)
    assert store.records(1) == []


def test_restore_and_compensation_validate_exact_identity():
    calls = []
    transaction = VisibilityTransaction([record(1)], [record(2)], lambda n:'object'+str(n),
                                        lambda r, visible: calls.append((r['object_id'], visible)))
    transaction.apply()
    assert calls == [('1',True), ('2',False)]
    transaction.rollback()
    assert calls[-2:] == [('2',True), ('1',False)]
    with pytest.raises(ValueError, match='identity changed'):
        VisibilityTransaction([], [record(2)], lambda _: 'different object', lambda *args:None)


@pytest.mark.parametrize('bad', [[record(1),record(1)], [{'object_id':'-1','name':'a'}],
                                [{'object_id':True,'name':'a'}], [{}]])
def test_invalid_visibility_records_rejected(bad):
    with pytest.raises(ValueError): hidden_records(bad)

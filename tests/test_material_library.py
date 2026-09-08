import pytest
from carla_safety_agent.material_library import MaterialLibrary, exact_environment_target
from carla_safety_agent.material_library import MaterialTransaction, material_edits


def test_exact_identity_only():
    assert exact_environment_target('House_1_SM_0', {'House_1','House_10'}) == 'House_1'
    with pytest.raises(ValueError): exact_environment_target('House_1', {'House_10'})
    with pytest.raises(ValueError): exact_environment_target('House_1_SM', {'House_1','House_1_SM'})


def test_texture_checksum_and_episode_history(tmp_path):
    library=MaterialLibrary(tmp_path)
    digest=library.put_texture(b'test texture bytes')
    assert library.texture(digest)==b'test texture bytes'
    library.record(1,'house','mesh',0,digest)
    assert len(MaterialLibrary(tmp_path).overrides(1))==1
    assert not library.overrides(2)
    library.record(1,'house','mesh',0,None)
    assert not library.overrides(1)
    with pytest.raises(ValueError): library.texture('../secret')


def edit(target='house', texture='a'*64):
    return {'target':target,'component':'mesh','slot':0,'texture':texture}


def test_material_version_removes_new_edits_and_rolls_back():
    calls = []
    transaction = MaterialTransaction([edit(),edit('road')], [edit(texture='b'*64)],
                                      lambda key, digest: calls.append((key,digest)))
    transaction.apply()
    assert calls == [(('house','mesh',0),'b'*64), (('road','mesh',0),None)]
    transaction.rollback()
    assert calls[-2:] == [(('road','mesh',0),'a'*64), (('house','mesh',0),'a'*64)]


def test_material_validation_rejects_duplicates_and_bad_references():
    with pytest.raises(ValueError, match='Duplicate'): material_edits([edit(),edit()])
    with pytest.raises(ValueError, match='digest'): material_edits([edit(texture='../file')])
    with pytest.raises(ValueError, match='identity'): material_edits([edit(target='house|csa')])


def test_material_rollback_continues_after_failure():
    calls = []
    def apply(key, digest):
        calls.append(key[0])
        if digest is None and key[0]=='road': raise RuntimeError('server unavailable')
    transaction = MaterialTransaction([], [edit(),edit('road')], apply)
    transaction.apply()
    with pytest.raises(RuntimeError, match='rollback incomplete'): transaction.rollback()
    assert calls == ['house','road','road','house']

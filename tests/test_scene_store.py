import pytest
from carla_safety_agent.scene_store import SceneStore, validate_scene


def document(x=1):
    return {'map':'Town04', 'objects':[{'stable_id':'stable', 'blueprint_id':'static.prop.box01',
        'transform':{'location':{'x':x,'y':0,'z':1},'rotation':{'pitch':0,'yaw':0,'roll':0}}}]}


def test_history_conflicts_and_restart(tmp_path):
    store = SceneStore(tmp_path)
    first = store.save(document(), 'scene')['head']
    with pytest.raises(ValueError): store.save(document(), 'scene', first['scene_id'])
    second = store.save(document(2), 'scene', first['scene_id'], first['version'])['head']
    undo = store.move(first['scene_id'], -1, second['version'])
    assert undo['document']['objects'][0]['transform']['location']['x'] == 1
    assert SceneStore(tmp_path).read(first['scene_id'])['head']['version'] == first['version']
    assert store.move(first['scene_id'], 1, first['version'])['head']['version'] == second['version']


@pytest.mark.parametrize('bad', ['../escape','/tmp/escape','a/b',''])
def test_paths_confined(tmp_path, bad):
    with pytest.raises(ValueError): SceneStore(tmp_path).read(bad)


def test_validation_and_branch_keep_old_versions(tmp_path):
    with pytest.raises(ValueError): validate_scene(document(float('nan')))
    store = SceneStore(tmp_path)
    first = store.save(document(), 'first')['head']
    second = store.save(document(2), 'second', first['scene_id'], first['version'])['head']
    store.move(first['scene_id'], -1, second['version'])
    branch = store.save(document(3), 'branch', first['scene_id'], first['version'])['head']
    assert second['version'] not in branch['history']
    assert store.read(first['scene_id'], second['version'])['document']['name'] == 'second'

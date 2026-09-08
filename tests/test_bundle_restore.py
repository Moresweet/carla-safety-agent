import json
import pytest
from test_studio_bridge import functions
from carla_safety_agent.project_bundle import export_bundle
from carla_safety_agent.scene_store import SceneStore
from carla_safety_agent.material_library import MaterialLibrary


def test_bundle_restore_delegates_explicit_version(tmp_path):
    store = SceneStore(tmp_path/'source/scenes')
    saved = store.save({'map':'Town04','objects':[]}, 'Imported')
    folder = tmp_path/'data/project-bundles'; folder.mkdir(parents=True)
    export_bundle(store.root, tmp_path/'source', [saved['head']['scene_id']], folder/'test.zip')
    calls = []
    env = functions('restore_bundle_scene', PROJECT_ROOT=tmp_path, json=json,
                    connect_world=lambda:None, MATERIALS=MaterialLibrary(tmp_path/'data'),
                    restore_scene_document=lambda value: calls.append(value) or {'ok':True})
    payload = {'bundle_id':'test', 'scene_id':saved['head']['scene_id'], 'version':saved['head']['version']}
    result = env['restore_bundle_scene'](payload)
    assert result['ok'] and not result['scene_history_installed']
    assert calls == [saved]
    with pytest.raises(ValueError): env['restore_bundle_scene']({**payload, 'version':'missing'})
    with pytest.raises(ValueError): env['restore_bundle_scene']({**payload, 'bundle_id':'../test'})
    with pytest.raises(ValueError): env['restore_bundle_scene']({'bundle_id':'test'})
    assert len(calls) == 1


def test_busy_world_rejects_bundle_before_file_access(tmp_path):
    def busy(): raise RuntimeError('evaluation active')
    env = functions('restore_bundle_scene', PROJECT_ROOT=tmp_path, connect_world=busy)
    with pytest.raises(RuntimeError, match='evaluation active'):
        env['restore_bundle_scene']({'bundle_id':'test','scene_id':'test','version':'test'})
    assert not (tmp_path/'data').exists()

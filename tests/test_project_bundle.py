import hashlib
import json
import zipfile

import pytest

from carla_safety_agent.project_bundle import export_bundle, import_bundle, read_bundle
from carla_safety_agent.scene_store import SceneStore


def fixture_bundle(tmp_path):
    store = SceneStore(tmp_path/'source/scenes')
    payload = b'test-texture-bytes'
    digest = hashlib.sha256(payload).hexdigest()
    textures = tmp_path/'source/textures'; textures.mkdir(parents=True)
    (textures/(digest+'.png')).write_bytes(payload)
    doc = {'map': 'Town04', 'objects': [], 'environment_materials': [
        {'target': 'building', 'component': 'mesh', 'slot': 0, 'texture': digest}]}
    first = store.save(doc, '迁移场景')
    scene_id = first['head']['scene_id']
    second = store.save({**doc, 'weather': {'precipitation': 75}}, '修改天气', scene_id, first['head']['version'])
    store.move(scene_id, -1, second['head']['version'])
    output = tmp_path/'project.zip'
    export_bundle(store.root, tmp_path/'source', [scene_id], output)
    return output, scene_id, first, second


def test_roundtrip_history_textures_and_independent_destination(tmp_path):
    output, scene_id, first, second = fixture_bundle(tmp_path)
    imported = import_bundle(output, tmp_path)
    store = SceneStore(imported/'data/scenes')
    assert store.read(scene_id)['document'] == first['document']
    assert store.move(scene_id, 1, first['head']['version'])['document'] == second['document']
    manifest, files = read_bundle(output)
    assert manifest['dependencies']['maps'] == ['Town04']
    assert not manifest['dependencies']['external_assets_included']
    for name, payload in files.items():
        if name.startswith('textures/'):
            assert (imported/'data'/name).read_bytes() == payload
    assert import_bundle(output, tmp_path) != imported


@pytest.mark.parametrize('damage', ['traversal', 'checksum', 'duplicate', 'dependency'])
def test_invalid_archive_rejected_without_import_directory(tmp_path, damage):
    output, *_ = fixture_bundle(tmp_path)
    with zipfile.ZipFile(output) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    if damage == 'traversal': files['../outside'] = b'bad'
    if damage == 'checksum':
        name = next(name for name in files if name.startswith('textures/')); files[name] = b'changed'
    if damage == 'dependency':
        manifest = json.loads(files['manifest.json']); manifest['dependencies']['maps'] = []
        files['manifest.json'] = json.dumps(manifest).encode()
    broken = tmp_path/'broken.zip'
    with zipfile.ZipFile(broken, 'w') as archive:
        for name, payload in files.items(): archive.writestr(name, payload)
        if damage == 'duplicate':
            with pytest.warns(UserWarning): archive.writestr('manifest.json', files['manifest.json'])
    with pytest.raises(ValueError): import_bundle(broken, tmp_path)
    assert not list(tmp_path.glob('carla-project-*'))

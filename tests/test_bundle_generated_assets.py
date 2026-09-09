import hashlib
import json
from pathlib import Path
import zipfile

import pytest

from carla_safety_agent.blender_package import export_asset
from carla_safety_agent.project_bundle import export_bundle, read_bundle, prepare_generated_assets
from carla_safety_agent.scene_store import SceneStore


def fixture(tmp_path):
    source = tmp_path/'source'; source.mkdir()
    (source/'asset.fbx').write_bytes(b'fbx source')
    (source/'texture.png').write_bytes(b'texture source')
    package = tmp_path/'asset.zip'
    export_asset(source, package, {'color':[.1,.2,.3,1], 'roughness':.5})
    blueprint = 'generated.prop.migrated_barrier'
    store = SceneStore(tmp_path/'scenes')
    saved = store.save({'map':'Town04', 'objects':[{
        'stable_id':'stable-barrier', 'blueprint_id':blueprint,
        'transform':{'location':dict(x=1,y=2,z=3),'rotation':dict(pitch=0,yaw=0,roll=0)}}]}, 'generated')
    return package, blueprint, store, saved['head']['scene_id']


def test_scene_bundle_carries_sources_and_prepares_without_execution(tmp_path, monkeypatch):
    package, blueprint, store, scene_id = fixture(tmp_path)
    archive = tmp_path/'project.zip'
    export_bundle(store.root, tmp_path, [scene_id], archive, generated_assets={blueprint:package})
    manifest, files = read_bundle(archive)
    digest = hashlib.sha256(package.read_bytes()).hexdigest()
    assert manifest['dependencies']['generated_asset_sources'] == {blueprint:digest}
    assert manifest['dependencies']['generated_assets_require_unreal_import']
    assert manifest['dependencies']['external_assets_included']
    assert not manifest['dependencies']['unreal_asset_binaries_included']
    assert files[f'generated-assets/{digest}.zip'] == package.read_bytes()
    monkeypatch.setattr('subprocess.run', lambda *a, **k: pytest.fail('Preparation must not execute assets'))
    target = tmp_path/'target'
    prepared = prepare_generated_assets(archive, target)
    job = prepared['assets'][blueprint]
    folder = Path(job['directory'])
    assert (folder/'asset.fbx').read_bytes() == b'fbx source'
    assert json.loads((folder/'request.json').read_text())['texture_path'] == str(folder/'texture.png')
    assert job['suggested_asset_name'] == 'migrated_barrier'
    assert not prepared['unreal_registered'] and not prepared['live_world_modified']
    assert not (target/'.runtime/blender-assets/registry.json').exists()


@pytest.mark.parametrize('bindings', ['missing', 'extra'])
def test_bindings_cover_all_history_dependencies(tmp_path, bindings):
    package, blueprint, store, scene_id = fixture(tmp_path)
    values = {} if bindings == 'missing' else {blueprint:package, 'generated.prop.unused':package}
    archive = tmp_path/'project.zip'
    with pytest.raises(ValueError, match='exactly'):
        export_bundle(store.root, tmp_path, [scene_id], archive, generated_assets=values)
    assert not archive.exists()


def test_nested_tamper_rejected_even_if_outer_hash_is_valid(tmp_path):
    package, blueprint, store, scene_id = fixture(tmp_path)
    with zipfile.ZipFile(package) as original:
        entries = {n:original.read(n) for n in original.namelist()}
    entries['asset.fbx'] = b'changed'
    broken = tmp_path/'broken.zip'
    with zipfile.ZipFile(broken, 'w') as archive:
        for name, payload in entries.items(): archive.writestr(name, payload)
    with pytest.raises(ValueError, match='checksum'):
        export_bundle(store.root, tmp_path, [scene_id], tmp_path/'project.zip', generated_assets={blueprint:broken})


def test_nested_expansion_limit_checked_before_preparation(tmp_path, monkeypatch):
    package, blueprint, store, scene_id = fixture(tmp_path)
    archive = tmp_path/'project.zip'
    export_bundle(store.root, tmp_path, [scene_id], archive, generated_assets={blueprint:package})
    _, files = read_bundle(archive)
    # Outer bytes fit; nested uncompressed source bytes exceed the remaining limit.
    monkeypatch.setattr('carla_safety_agent.project_bundle.LIMIT', sum(map(len, files.values())) + 1)
    with pytest.raises(ValueError, match='Expanded'):
        prepare_generated_assets(archive, tmp_path/'target')
    assert not (tmp_path/'target').exists()


def test_shared_source_package_is_extracted_only_once(tmp_path):
    package, blueprint, store, scene_id = fixture(tmp_path)
    prior = store.read(scene_id)
    document = prior['document']
    second = 'generated.prop.second_barrier'
    document['objects'].append({**document['objects'][0], 'stable_id':'second', 'blueprint_id':second})
    store.save(document, 'two aliases', scene_id, prior['head']['version'])
    archive = tmp_path/'shared.zip'
    export_bundle(store.root, tmp_path, [scene_id], archive, generated_assets={blueprint:package, second:package})
    result = prepare_generated_assets(archive, tmp_path/'target')
    assert result['assets'][blueprint]['job_id'] == result['assets'][second]['job_id']
    assert len(list((tmp_path/'target/.runtime/blender-assets').iterdir())) == 1

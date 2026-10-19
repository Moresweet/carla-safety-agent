import hashlib
import json
from pathlib import Path
import zipfile

import pytest

from carla_safety_agent.blender_package import export_asset
from carla_safety_agent.project_bundle import export_bundle, read_bundle, prepare_generated_assets
from carla_safety_agent.scene_store import SceneStore


@pytest.mark.parametrize('tamper', [False, True])
def test_offline_restore_verifier_checks_imported_bytes(tmp_path, monkeypatch, tamper):
    import importlib.util
    spec = importlib.util.spec_from_file_location('offline_restore', Path(__file__).resolve().parents[1]/'tools/verify_bundle_offline_restore.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    package, blueprint, store, scene_id = fixture(tmp_path)
    archive = tmp_path/'verify.zip'
    export_bundle(store.root,tmp_path,[scene_id],archive,generated_assets={blueprint:package})
    original = module.import_bundle
    if tamper:
        def damaged(*args):
            destination = original(*args)
            (destination/'data/generated-assets/index.json').write_bytes(b'changed')
            return destination
        monkeypatch.setattr(module,'import_bundle',damaged)
        with pytest.raises(ValueError,match='Imported payload mismatch'):
            module.verify(archive,tmp_path)
    else:
        result = module.verify(archive,tmp_path)
        assert result['ok'] and result['verified_asset_sources'] == 2
        assert not result['live_world_modified']


@pytest.mark.parametrize('damage', [None, 'map', 'payload'])
def test_explicit_legacy_flag_migration_preserves_source(tmp_path, damage):
    from carla_safety_agent.project_bundle import migrate_legacy_asset_flags
    package, blueprint, store, scene_id = fixture(tmp_path)
    current = tmp_path/'current.zip'
    export_bundle(store.root, tmp_path, [scene_id], current, generated_assets={blueprint:package})
    manifest, files = read_bundle(current)
    manifest['dependencies']['external_assets_included'] = False
    del manifest['dependencies']['unreal_asset_binaries_included']
    if damage == 'map': manifest['dependencies']['maps'] = []
    if damage == 'payload': files[next(n for n in files if n.startswith('scenes/'))] += b'changed'
    legacy = tmp_path/'legacy.zip'
    with zipfile.ZipFile(legacy, 'w') as archive:
        archive.writestr('manifest.json', json.dumps(manifest))
        for name, payload in files.items(): archive.writestr(name,payload)
    before = legacy.read_bytes()
    output = tmp_path/'migrated.zip'
    with pytest.raises(ValueError): read_bundle(legacy)
    if damage:
        with pytest.raises(ValueError): migrate_legacy_asset_flags(legacy,output)
        assert not output.exists()
    else:
        result = migrate_legacy_asset_flags(legacy,output)
        assert result['payloads_unchanged'] and read_bundle(output)[1] == files
        with pytest.raises(ValueError): migrate_legacy_asset_flags(legacy,output)
    assert legacy.read_bytes() == before


@pytest.mark.parametrize('damage', [None, 'map', 'payload'])
def test_real_legacy_project_reference_protection(tmp_path, damage):
    from carla_safety_agent.capture_references import project_references
    package, blueprint, store, scene_id = fixture(tmp_path, name='capture-retained-legacy')
    current = tmp_path/'current.zip'
    export_bundle(store.root, tmp_path, [scene_id], current, generated_assets={blueprint:package})
    manifest, files = read_bundle(current)
    manifest['dependencies']['external_assets_included'] = False
    del manifest['dependencies']['unreal_asset_binaries_included']
    if damage == 'map': manifest['dependencies']['maps'] = []
    if damage == 'payload': files[next(n for n in files if n.startswith('scenes/'))] += b'changed'
    bundles = tmp_path/'bundles'; bundles.mkdir()
    legacy = bundles/'legacy.zip'
    with zipfile.ZipFile(legacy, 'w') as archive:
        archive.writestr('manifest.json', json.dumps(manifest))
        for name, payload in files.items(): archive.writestr(name, payload)
    before = legacy.read_bytes()
    result = project_references(bundles)
    assert not result['complete'] and result['warnings']
    assert ('capture-retained-legacy' in result['references']) == (damage is None)
    assert legacy.read_bytes() == before


def test_nested_asset_metadata_retains_capture_references(tmp_path):
    from carla_safety_agent.capture_references import project_references
    package, blueprint, store, scene_id = fixture(tmp_path)
    with zipfile.ZipFile(package) as archive:
        payloads = {name: archive.read(name) for name in archive.namelist()}
    manifest = json.loads(payloads['manifest.json'])
    manifest['note'] = 'capture-asset-source'
    payloads['manifest.json'] = json.dumps(manifest).encode()
    annotated = tmp_path/'annotated.zip'
    with zipfile.ZipFile(annotated, 'w') as archive:
        for name, payload in payloads.items(): archive.writestr(name, payload)
    bundles = tmp_path/'bundles'; bundles.mkdir()
    output = bundles/'project.zip'
    export_bundle(store.root, tmp_path, [scene_id], output, generated_assets={blueprint:annotated})
    before = output.read_bytes()
    result = project_references(bundles)
    assert result['complete']
    refs = result['references']['capture-asset-source']
    assert len(refs) == 1 and refs[0]['entry'].endswith('.zip!manifest.json')
    assert output.read_bytes() == before


def fixture(tmp_path, name='generated'):
    source = tmp_path/'source'; source.mkdir()
    (source/'asset.fbx').write_bytes(b'fbx source')
    (source/'texture.png').write_bytes(b'texture source')
    package = tmp_path/'asset.zip'
    export_asset(source, package, {'color':[.1,.2,.3,1], 'roughness':.5})
    blueprint = 'generated.prop.migrated_barrier'
    store = SceneStore(tmp_path/'scenes')
    saved = store.save({'map':'Town04', 'objects':[{
        'stable_id':'stable-barrier', 'blueprint_id':blueprint,
        'transform':{'location':dict(x=1,y=2,z=3),'rotation':dict(pitch=0,yaw=0,roll=0)}}]}, name)
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

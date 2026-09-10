import json
import pytest
from carla_safety_agent.bundle_registration import register_bundle
from carla_safety_agent.project_bundle import export_bundle, read_bundle
from test_bundle_generated_assets import fixture


def setup(tmp_path):
    package, blueprint, store, scene_id = fixture(tmp_path)
    archive = tmp_path/'project.zip'
    export_bundle(store.root, tmp_path, [scene_id], archive, generated_assets={blueprint:package})
    target = tmp_path/'target'
    importer = target/'integration/carla/import_generated_asset.py'
    importer.parent.mkdir(parents=True); importer.write_text('# test importer')
    return archive, target, blueprint


def test_registration_remaps_new_bundle_only(tmp_path, monkeypatch):
    archive, target, original = setup(tmp_path)
    before = archive.read_bytes()
    def success(self, job, name, *, require_clean_exit):
        assert require_clean_exit
        return {'blueprint_id':'generated.prop.'+name.lower(), 'import_returncode':0, 'import_log':'test-log'}
    monkeypatch.setattr('carla_safety_agent.blender_pipeline.BlenderPipeline.import_to_carla', success)
    output = tmp_path/'remapped.zip'
    result = register_bundle(archive,target,output,execute=True)
    assert archive.read_bytes() == before
    manifest, files = read_bundle(output)
    replacement = result['blueprint_replacements'][original]
    assert replacement != original and manifest['dependencies']['blueprints'] == [replacement]
    scene = next(json.loads(p) for n,p in files.items() if n.startswith('scenes/') and not n.endswith('/head.json'))
    assert scene['objects'][0]['stable_id'] == 'stable-barrier'
    assert scene['objects'][0]['blueprint_id'] == replacement
    assert not result['restored'] and not result['live_world_modified']


def test_failed_import_retains_attention_report_no_output(tmp_path, monkeypatch):
    archive, target, _ = setup(tmp_path)
    def fail(*a, **kw): raise RuntimeError('native failure')
    monkeypatch.setattr('carla_safety_agent.blender_pipeline.BlenderPipeline.import_to_carla', fail)
    output = tmp_path/'remapped.zip'
    with pytest.raises(RuntimeError,match='Migration incomplete'):
        register_bundle(archive,target,output,execute=True)
    report = json.loads(next((target/'.runtime/blender-assets/migrations').glob('*/report.json')).read_text())
    assert report['state'] == 'needs_attention'
    assert not output.exists()


def test_execution_requires_explicit_opt_in(tmp_path):
    with pytest.raises(ValueError,match='Explicit'):
        register_bundle(tmp_path/'missing.zip',tmp_path/'target',tmp_path/'output.zip')
    assert not (tmp_path/'target').exists()

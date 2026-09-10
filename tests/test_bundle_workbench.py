import io
import json
import zipfile
import pytest
from carla_safety_agent.bundle_workbench import BundleWorkbench
from carla_safety_agent.scene_store import SceneStore


def fixture(tmp_path):
    scene=SceneStore(tmp_path/'data/scenes').save({'map':'Town04','objects':[]},'Portable')
    return BundleWorkbench(tmp_path),scene['head']['scene_id']


def test_ui_roundtrip_isolated_and_never_overwrites_active_catalog(tmp_path):
    service,scene=fixture(tmp_path)
    exported=service.export({'scene_ids':[scene]})
    assert exported['manifest']['dependencies']['weights_included'] is False
    assert exported['dependency_availability']=='not_checked'
    payload=service.download(exported['bundle_id'])
    uploaded=service.upload(payload)
    assert uploaded['bundle_id']!=exported['bundle_id']
    before=SceneStore(tmp_path/'data/scenes').read(scene)
    first=service.import_isolated({'bundle_id':uploaded['bundle_id'],'confirmed':True})
    second=service.import_isolated({'bundle_id':uploaded['bundle_id'],'confirmed':True})
    assert first['directory']!=second['directory']
    assert not first['active_scene_catalog_modified'] and not first['live_world_modified']
    assert SceneStore(tmp_path/'data/scenes').read(scene)==before
    assert service.inspect(uploaded['bundle_id'])['manifest']==exported['manifest']


@pytest.mark.parametrize('data',[{}, {'scene_ids':[]},{'scene_ids':['../bad']},
    {'scene_ids':['a'],'include_material_previews':1},{'scene_ids':['a'],'output':'/tmp/out'},
    {'scene_ids':['a','a']}, {'scene_ids':[1]}, {'scene_ids':['a'],'include_generated_sources':1}])
def test_invalid_export_does_not_create_archive(tmp_path,data):
    service=BundleWorkbench(tmp_path)
    with pytest.raises(ValueError): service.export(data)
    assert not service.root.exists()


def test_upload_checks_archive_before_staging(tmp_path):
    service=BundleWorkbench(tmp_path)
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w') as archive: archive.writestr('../escape','bad')
    with pytest.raises(ValueError): service.upload(stream.getvalue())
    assert not service.root.exists()


def test_import_requires_explicit_confirmation_and_confined_identity(tmp_path):
    service=BundleWorkbench(tmp_path)
    for data in ({'bundle_id':'x','confirmed':1},{'bundle_id':'x'}, {'bundle_id':'x','confirmed':True,'path':'/tmp'}):
        with pytest.raises(ValueError): service.import_isolated(data)
    with pytest.raises(ValueError): service.path('../escape')
    with service.operation():
        with pytest.raises(ValueError,match='Another'): service.inspect('x')


def test_redirected_archive_root_is_rejected_before_writing(tmp_path):
    service,scene=fixture(tmp_path/'project')
    outside=tmp_path/'outside';outside.mkdir()
    service.root.symlink_to(outside,target_is_directory=True)
    with pytest.raises(ValueError): service.export({'scene_ids':[scene]})
    assert not list(outside.iterdir())


def test_browser_upload_limit(tmp_path):
    service=BundleWorkbench(tmp_path)
    for payload in (b'',b'x'*(16*1024*1024+1)):
        with pytest.raises(ValueError,match='16 MiB'): service.upload(payload)
    assert not service.root.exists()


def source_fixture(tmp_path):
    service,scene=fixture(tmp_path)
    store=SceneStore(tmp_path/'data/scenes')
    saved=store.read(scene)
    bp='generated.prop.fixture'
    document={**saved['document'],'objects':[{'stable_id':'asset','blueprint_id':bp,
        'transform':{'location':{'x':1,'y':2,'z':3},'rotation':{'pitch':0,'yaw':0,'roll':0}}}]}
    store.save(document,'With source',scene,saved['head']['version'])
    root=tmp_path/'.runtime/blender-assets';job=root/'job123';job.mkdir(parents=True)
    (job/'asset.fbx').write_bytes(b'bounded test FBX')
    (job/'secret.txt').write_bytes(b'never package arbitrary files')
    (job/'request.json').write_text(json.dumps({'color':[.1,.2,.3,1.],'roughness':.4}))
    registry={bp:{'blueprint_id':bp,'mesh_path':'/Game/Fixture','source_fbx':str(job/'asset.fbx')}}
    (root/'registry.json').write_text(json.dumps(registry))
    return service,scene,job,bp


def test_sources_include_history_and_preserve_exact_snapshot(tmp_path,monkeypatch):
    from carla_safety_agent.project_bundle import read_bundle
    from carla_safety_agent.blender_package import read_asset
    service,scene,job,bp=source_fixture(tmp_path)
    store=SceneStore(tmp_path/'data/scenes');before=store.read(scene)
    original=service._source_packages
    def concurrent_change(manifest,work):
        store.save({'map':'Town05','objects':[]},'Later edit',scene,before['head']['version'])
        return original(manifest,work)
    monkeypatch.setattr(service,'_source_packages',concurrent_change)
    result=service.export({'scene_ids':[scene],'include_generated_sources':True})
    manifest,files=read_bundle(service.path(result['bundle_id']))
    assert manifest['dependencies']['maps']==['Town04']
    bindings=manifest['dependencies']['generated_asset_sources'];assert set(bindings)=={bp}
    _,asset=read_asset(io.BytesIO(files['generated-assets/'+bindings[bp]+'.zip']))
    assert asset=={'asset.fbx':(job/'asset.fbx').read_bytes()}
    assert store.read(scene)['document']['map']=='Town05'
    assert manifest['dependencies']['weights_included'] is False


@pytest.mark.parametrize('damage',['missing','source_outside','source_symlink','request_symlink','parameters','texture_outside'])
def test_unresolved_source_refuses_final_archive(tmp_path,damage):
    service,scene,job,bp=source_fixture(tmp_path)
    if damage=='missing':(job/'asset.fbx').unlink()
    if damage=='source_outside':
        registry=json.loads((job.parent/'registry.json').read_text());registry[bp]['source_fbx']=str(tmp_path/'asset.fbx')
        (tmp_path/'asset.fbx').write_bytes(b'external');(job.parent/'registry.json').write_text(json.dumps(registry))
    if damage=='source_symlink':
        (job/'asset.fbx').unlink();(tmp_path/'external').write_bytes(b'external');(job/'asset.fbx').symlink_to(tmp_path/'external')
    if damage=='request_symlink':
        (job/'request.json').rename(tmp_path/'request.json');(job/'request.json').symlink_to(tmp_path/'request.json')
    if damage=='parameters':(job/'request.json').write_text('{}')
    if damage=='texture_outside':(job/'request.json').write_text(json.dumps({'texture_path':'/tmp/external.png'}))
    with pytest.raises(ValueError):service.export({'scene_ids':[scene],'include_generated_sources':True})
    assert not list(service.root.glob('*.zip'))
    assert SceneStore(tmp_path/'data/scenes').read(scene)['document']['objects'][0]['blueprint_id']==bp


def test_explicit_runtime_hash_document_never_reads_weight_paths(tmp_path):
    from carla_safety_agent.project_bundle import read_bundle
    service,scene=fixture(tmp_path)
    reference={'schema_version':'carla-runtime-reference/1','files':[
        {'model':'vad','role':role,'root':'models','path':role+'.bin','size':10,'sha256':'a'*64}
        for role in ('adapter','checkpoint')]}
    result=service.export({'scene_ids':[scene],'include_generated_sources':True,'runtime_reference':reference})
    manifest,files=read_bundle(service.path(result['bundle_id']))
    assert json.loads(files['runtime/reference.json'])==reference
    assert manifest['dependencies']['model_ids']==['vad']
    assert not manifest['dependencies']['weights_included']
    assert not any(name.endswith('.bin') for name in files)
    with pytest.raises(ValueError):service.export({'scene_ids':[scene],'runtime_reference':{'path':'/etc/passwd'}})

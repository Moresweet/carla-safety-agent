import io
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
    {'scene_ids':['a','a']}, {'scene_ids':[1]}])
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

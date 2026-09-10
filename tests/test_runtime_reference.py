import copy
import json

import pytest

from carla_safety_agent.runtime_reference import export_reference, validate_reference, verify_reference


def fixture(tmp_path):
    source=tmp_path/'source';source.mkdir()
    (source/'agent.py').write_text('raise RuntimeError("must not execute")')
    (source/'weights.pth').write_bytes(b'not a pickle; only hash these bytes')
    catalog=[{'id':'vad','status':'available','adapter':str(source/'agent.py'),
              'checkpoint':str(source/'weights.pth'),'config':None}]
    document=export_reference(catalog,['vad'],{'zoo':source})
    return source,document


def test_relocation_matches_without_loading_or_executing(tmp_path):
    source,document=fixture(tmp_path)
    target=tmp_path/'another-machine';target.mkdir()
    for path in source.iterdir():(target/path.name).write_bytes(path.read_bytes())
    assert str(tmp_path) not in json.dumps(document)
    result=verify_reference(document,{'zoo':target})
    assert result['ok'] and not result['weights_loaded'] and not result['code_executed']
    (target/'weights.pth').write_bytes(b'changed')
    assert not verify_reference(document,{'zoo':target})['ok']
    assert all(row['state']=='missing_root' for row in verify_reference(document,{})['files'])


@pytest.mark.parametrize('path',['../secret','/absolute','a/../secret','a//b','C:\\secret','.','a\x00b'])
def test_unsafe_relative_paths_rejected(tmp_path,path):
    _,document=fixture(tmp_path)
    document['files'][0]['path']=path
    with pytest.raises(ValueError):validate_reference(document)


def test_incomplete_roles_and_symlink_escape_rejected(tmp_path):
    source,document=fixture(tmp_path)
    incomplete=copy.deepcopy(document);incomplete['files']=incomplete['files'][:1]
    with pytest.raises(ValueError):validate_reference(incomplete)
    outside=tmp_path/'outside';outside.write_bytes((source/'weights.pth').read_bytes())
    (source/'weights.pth').unlink();(source/'weights.pth').symlink_to(outside)
    assert not verify_reference(document,{'zoo':source})['ok']


def test_reference_bundle_roundtrip_contains_no_weights(tmp_path):
    from carla_safety_agent.project_bundle import export_bundle,read_bundle,import_bundle
    from carla_safety_agent.scene_store import SceneStore
    _,document=fixture(tmp_path)
    reference=tmp_path/'reference.json';reference.write_text(json.dumps(document))
    store=SceneStore(tmp_path/'scenes')
    scene=store.save({'map':'Town04','objects':[]},'portable')
    output=tmp_path/'bundle.zip'
    export_bundle(store.root,tmp_path,[scene['head']['scene_id']],output,runtime_reference=reference)
    manifest,files=read_bundle(output)
    assert manifest['dependencies']['model_ids']==['vad']
    assert manifest['dependencies']['runtime_reference_included']
    assert not manifest['dependencies']['weights_included']
    assert all(not name.endswith('.pth') for name in files)
    imported=import_bundle(output,tmp_path)
    assert json.loads((imported/'data/runtime/reference.json').read_text())==document

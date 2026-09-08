import json
import zipfile
import pytest
from carla_safety_agent.blender_package import export_asset, import_asset, read_asset


def test_asset_roundtrip_rebases_paths_without_registry(tmp_path):
    source=tmp_path/'source'; source.mkdir()
    for name in ('asset.fbx','asset.blend','asset.glb','texture.png'): (source/name).write_bytes(name.encode())
    package=tmp_path/'asset.zip'
    parameters={'color':[.1,.2,.3,1],'roughness':.4}
    export_asset(source,package,parameters)
    imported=import_asset(package,tmp_path/'target')
    from pathlib import Path
    folder=Path(imported['directory'])
    request=json.loads((folder/'request.json').read_text())
    assert request=={**parameters,'texture_path':str(folder/'texture.png')}
    assert json.loads((folder/'manifest.json').read_text())['outputs']['fbx']==str(folder/'asset.fbx')
    assert not (folder.parent/'registry.json').exists()
    for name in ('asset.fbx','asset.blend','asset.glb','texture.png'): assert (folder/name).read_bytes()==(source/name).read_bytes()
    assert not imported['asset_executed']


def test_asset_tamper_rejected_before_destination_creation(tmp_path):
    source=tmp_path/'source';source.mkdir();(source/'asset.fbx').write_bytes(b'original')
    package=tmp_path/'asset.zip';export_asset(source,package,{'color':[1,1,1,1],'roughness':.5})
    manifest,_=read_asset(package)
    broken=tmp_path/'broken.zip'
    with zipfile.ZipFile(broken,'w') as archive:
        archive.writestr('manifest.json',json.dumps(manifest));archive.writestr('asset.fbx',b'changed')
    with pytest.raises(ValueError,match='checksum'):import_asset(broken,tmp_path/'target')
    assert not (tmp_path/'target').exists()

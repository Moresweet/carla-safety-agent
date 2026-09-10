import json
import pytest
from carla_safety_agent.material_catalog_merge import merge_preview_catalog


def fixture(tmp_path):
    folder=tmp_path/'source'; folder.mkdir()
    mesh={'triangleCount':1,'vertices':[0,0,0,0,0]*3}
    (folder/'mesh.json').write_text(json.dumps(mesh))
    catalog={'schema_version':'carla-material-catalog/1','map':'/Game/Carla/Maps/Town04',
        'actors':{'road':[{'component':'mesh','slots':[{'slot':0,'status':'uv0_ready','mesh_file':'mesh.json','triangles':1}]}]}}
    path=folder/'preview-catalog.json'; path.write_text(json.dumps(catalog))
    return path,catalog


def test_additive_merge_repeats_without_overwrite(tmp_path):
    source,catalog=fixture(tmp_path)
    first=merge_preview_catalog(source,tmp_path/'data')
    second=merge_preview_catalog(source,tmp_path/'data')
    assert first==second and first['world_modified'] is False
    catalog['actors']['other']=catalog['actors'].pop('road')
    source.write_text(json.dumps(catalog))
    merge_preview_catalog(source,tmp_path/'data')
    saved=json.loads((tmp_path/'data/material-exports/Town04/preview-catalog.json').read_text())
    assert set(saved['actors'])=={'road','other'}


@pytest.mark.parametrize('failure',['target','mesh'])
def test_conflict_preserves_existing_catalog_and_mesh(tmp_path,failure):
    source,catalog=fixture(tmp_path)
    merge_preview_catalog(source,tmp_path/'data')
    destination=tmp_path/'data/material-exports/Town04'
    before={p.name:p.read_bytes() for p in destination.iterdir()}
    if failure=='target':
        catalog['actors']['road'][0]['component']='changed'
        source.write_text(json.dumps(catalog))
    else:
        (source.parent/'mesh.json').write_text(json.dumps({'triangleCount':1,'vertices':[1,0,0,0,0]*3}))
    with pytest.raises(ValueError,match='differs'): merge_preview_catalog(source,tmp_path/'data')
    assert {p.name:p.read_bytes() for p in destination.iterdir()}==before


@pytest.mark.parametrize('name',['../mesh.json','/tmp/mesh.json'])
def test_bad_path_rejected_before_destination_creation(tmp_path,name):
    source,catalog=fixture(tmp_path)
    catalog['actors']['road'][0]['slots'][0]['mesh_file']=name
    source.write_text(json.dumps(catalog))
    with pytest.raises(ValueError): merge_preview_catalog(source,tmp_path/'data')
    assert not (tmp_path/'data').exists()

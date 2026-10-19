from types import SimpleNamespace as NS
import pytest
from carla_safety_agent.map_projection_archive import archive_map_projection,read_map_projection

XML='<OpenDRIVE><header><geoReference>+proj=tmerc +lat_0=0</geoReference></header></OpenDRIVE>'


def test_archive_roundtrip_is_independent_of_live_map(tmp_path):
    road=NS(name='Town04',to_opendrive=lambda:XML)
    ref=archive_map_projection(tmp_path,road)
    road.name='Town05';road.to_opendrive=lambda:'changed'
    assert ref['map_name']=='Town04'
    assert read_map_projection(tmp_path,ref)==XML


@pytest.mark.parametrize('xml',['','<bad>','<OpenDRIVE/>','<!DOCTYPE x><OpenDRIVE/>'])
def test_invalid_map_is_explicit_not_a_default_projection(tmp_path,xml):
    ref=archive_map_projection(tmp_path,NS(name='Town04',to_opendrive=lambda:xml))
    assert ref['state']=='unavailable' and not list(tmp_path.iterdir())


@pytest.mark.parametrize('damage',['hash','metadata','path','link'])
def test_tampered_or_linked_archive_refused(tmp_path,damage):
    ref=archive_map_projection(tmp_path,NS(name='Town04',to_opendrive=lambda:XML))
    path=tmp_path/ref['path']
    if damage=='hash':path.write_text(XML+' ')
    elif damage=='metadata':ref['geo_reference']='wrong'
    elif damage=='path':ref['path']='../map.xodr'
    else:path.unlink();path.symlink_to('/nonexistent')
    with pytest.raises(ValueError):read_map_projection(tmp_path,ref)

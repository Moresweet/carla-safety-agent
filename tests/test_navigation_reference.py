import copy
import math
import numpy as np
import pytest
from carla_safety_agent.navigation_reference import navigation_diagnostic


def anchor():
    return {'frame':10,'model_step':4,'navigation_reference':{
        'schema_version':'driveadapter-navigation-observation/1',
        'source':'original_tick_smoothed_gps','model_step':4,
        'world_xy_m':[103.,204.],'compass_rad':math.pi}}


def test_generation_reference_offset_and_heading_wrap():
    pose=np.eye(4);pose[:3,3]=[100,200,8];pose[:2,:2]=[[0,-1],[1,0]]
    saved=anchor();before=copy.deepcopy(saved)
    result=navigation_diagnostic(saved,pose)
    assert result['world_delta_xy_m']==[3,4]
    assert result['position_delta_m']==5
    assert result['heading_delta_rad']==pytest.approx(0)
    assert result['source_frame']==10
    assert result['reference_equivalence_verified'] is False
    assert result['measurement_kind']=='unconverted_coordinate_difference'
    assert saved==before
    saved['navigation_reference']['compass_rad']+=2*math.pi
    assert navigation_diagnostic(saved,pose)['heading_delta_rad']==pytest.approx(0,abs=1e-12)


@pytest.mark.parametrize('field,value',[
    ('schema_version','unknown'),('source','raw_gps'),('model_step',True),
    ('model_step',5),('world_xy_m',[1]),('world_xy_m',[True,2]),
    ('world_xy_m',[float('inf'),0]),('compass_rad',None),
    ('compass_rad',float('nan')),('compass_rad','1'),('world_xy_m',[1e20,0])])
def test_invalid_observation_is_not_reported_as_zero_error(field,value):
    saved=anchor();saved['navigation_reference'][field]=value
    result=navigation_diagnostic(saved,np.eye(4))
    assert result['state']=='unavailable' and 'position_delta_m' not in result


def test_legacy_data_is_explicitly_unavailable():
    assert navigation_diagnostic({'frame':10},np.eye(4))['state']=='unavailable'

import math
import numpy as np
import pytest
from test_prediction_trajectory import sample
from carla_safety_agent.projected_prediction import project_driveadapter_prediction


def saved():
    d=sample('driveadapter')
    d['planning_anchor']['navigation_reference']={
        'schema_version':'driveadapter-navigation-observation/1','model_step':1,
        'world_xy_m':[100.,200.],'compass_rad':math.pi/2,
        'source':'original_tick_smoothed_gps'}
    return d


def test_each_point_is_projected_not_just_origin_shift():
    calls=[]
    def convert(lat,lon):
        calls.append((lat,lon))
        return [lon*111319.490945*2,-lat*111324.60662786*3]
    result=project_driveadapter_prediction(saved(),np.eye(4),convert)
    assert len(calls)==5
    assert result['projected_navigation_world_xy_m']==pytest.approx([200,600])
    assert result['points'][0]['xyz_m']==pytest.approx([204,630,0])
    assert result['timing_verified'] is False and result['error_metrics_computed'] is False


def test_rotation_then_projection_then_current_body_transform():
    d=saved();d['planning_anchor']['navigation_reference']['compass_rad']=math.pi
    pose=np.eye(4);pose[0,3]=5
    result=project_driveadapter_prediction(d,pose,lambda lat,lon:[lon*111319.490945,-lat*111324.60662786])
    assert result['points'][0]['xyz_m']==pytest.approx([85,202,0])


@pytest.mark.parametrize('value',[[float('nan'),0],[1],[[1,2]]])
def test_invalid_native_conversion_rejected(value):
    with pytest.raises(ValueError):project_driveadapter_prediction(saved(),np.eye(4),lambda *_:value)


def test_no_legacy_navigation_fallback_or_extra_calls():
    def unexpected(*_):raise AssertionError('Should not project')
    with pytest.raises(ValueError):project_driveadapter_prediction(sample('driveadapter'),np.eye(4),unexpected)


def test_saved_parameters_override_legacy_constants():
    d=saved();d['planning_anchor']['navigation_reference'].update(
        schema_version='driveadapter-navigation-observation/2',
        coordinate_frame='original_route_planner_xy_not_carla_world',
        gps_mean_lat_lon=[10.,20.],gps_scale_lat_lon=[100.,200.])
    calls=[]
    def convert(lat,lon):calls.append((lat,lon));return [lon,lat]
    result=project_driveadapter_prediction(d,np.eye(4),convert)
    assert calls[0]==pytest.approx((8.,20.5))
    assert result['navigation_parameter_source']=='saved_runtime_parameters'
    d['planning_anchor']['navigation_reference']['gps_scale_lat_lon'][0]=0
    with pytest.raises(ValueError):project_driveadapter_prediction(d,np.eye(4),convert)

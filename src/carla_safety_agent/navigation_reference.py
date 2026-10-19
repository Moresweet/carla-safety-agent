"""Navigation-vs-ground-truth diagnostics; never prediction accuracy metrics."""
import math


def navigation_parameters(value):
    schema=value.get('schema_version')
    if schema=='driveadapter-navigation-observation/1':
        return [0.,0.],[111324.60662786,111319.490945],'reviewed_legacy_constants'
    if schema!='driveadapter-navigation-observation/2' or value.get('coordinate_frame')!='original_route_planner_xy_not_carla_world':
        raise ValueError('Unknown navigation coordinate convention')
    mean=value.get('gps_mean_lat_lon');scale=value.get('gps_scale_lat_lon')
    for pair in (mean,scale):
        if not isinstance(pair,list) or len(pair)!=2 or any(type(x) not in (int,float) or not math.isfinite(x) for x in pair):
            raise ValueError('Invalid saved navigation parameters')
    if not -90<=mean[0]<=90 or not -180<=mean[1]<=180 or any(not 0<x<=1e7 for x in scale):
        raise ValueError('Navigation parameters out of bounds')
    return mean,scale,'saved_runtime_parameters'


def navigation_diagnostic(anchor, origin):
    """Caller supplies a validated rigid generation pose, not the replay pose."""
    missing={'state':'unavailable','reason':'No valid saved navigation observation'}
    value=anchor.get('navigation_reference')
    if not isinstance(value,dict):return missing
    try:navigation_parameters(value)
    except ValueError:return missing
    if (value.get('source')!='original_tick_smoothed_gps' or
            type(value.get('model_step')) is not int or
            value['model_step']!=anchor.get('model_step')):return missing
    xy=value.get('world_xy_m');compass=value.get('compass_rad')
    if not isinstance(xy,list) or len(xy)!=2:return missing
    if any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>1e7
           for v in [*xy,compass]):return missing
    dx=float(xy[0]-origin[0,3]);dy=float(xy[1]-origin[1,3])
    heading=math.atan2(origin[1,0],origin[0,0])
    delta=compass-math.pi/2-heading
    return {'state':'available','source_frame':anchor['frame'],
            'measurement_kind':'unconverted_coordinate_difference',
            'world_delta_xy_m':[dx,dy],'position_delta_m':math.hypot(dx,dy),
            'heading_delta_rad':math.atan2(math.sin(delta),math.cos(delta)),
            'reference_equivalence_verified':False,
            'note':'Different coordinate representations; not physical localization error or prediction ADE/FDE'}

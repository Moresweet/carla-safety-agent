"""Map-project every DriveAdapter point; never apply a fixed positional offset."""
import math
import numpy as np
from .prediction_trajectory import replay_prediction, raw_points
from .navigation_reference import navigation_parameters


def project_driveadapter_prediction(metadata, current_pose, geo_to_xy):
    """geo_to_xy converts (latitude, longitude) using the archived map only.

    This numerical layer does not connect to CARLA or choose a current map.
    Original v1 navigation observations use the locally audited fixed scales.
    """
    checked=replay_prediction(metadata,current_pose)
    if (checked.get('state')!='available' or
            checked['contract']['model']!='driveadapter' or
            (checked.get('navigation_diagnostic') or {}).get('state')!='available'):
        raise ValueError('Reviewed DriveAdapter prediction and navigation observation required')
    anchor=metadata['planning_anchor'];nav=anchor['navigation_reference']
    origin=np.asarray(anchor['ego_matrix'],dtype=float)
    inverse=np.linalg.inv(np.asarray(current_pose,dtype=float))
    theta=nav['compass_rad']-math.pi/2
    c,s=math.cos(theta),math.sin(theta)
    base=np.asarray(nav['world_xy_m'],dtype=float)
    mean,scale,parameter_source=navigation_parameters(nav)

    def convert(model_xy):
        latitude=-float(model_xy[1])/scale[0]+mean[0]
        longitude=float(model_xy[0])/scale[1]+mean[1]
        if not -90<=latitude<=90 or not -180<=longitude<=180:
            raise ValueError('Model coordinate outside geodetic domain')
        xy=np.asarray(geo_to_xy(latitude,longitude),dtype=float)
        if xy.shape!=(2,) or not np.isfinite(xy).all():
            raise ValueError('Map conversion returned invalid coordinates')
        return xy

    projected_origin=convert(base)
    points=[]
    for i,(right,forward) in enumerate(raw_points(metadata,'driveadapter')):
        model_xy=base+np.array([c*forward-s*right,s*forward+c*right])
        xy=convert(model_xy)
        xyz=(inverse@np.array([*xy,origin[2,3],1.]))[:3].tolist()
        points.append({'step':i+1,'dt_s':None,'xyz_m':xyz})
    return {'state':'available','points':points,'source_frame':anchor['frame'],
            'navigation_parameter_source':parameter_source,
            'projected_navigation_world_xy_m':projected_origin.tolist(),
            'navigation_position_delta_m':float(np.linalg.norm(projected_origin-origin[:2,3])),
            'source':'driveadapter_fixed_scale_inverse_then_archived_map_projection',
            'timing_verified':False,'error_metrics_computed':False,
            'height_policy':'Generation ego height; road elevation not inferred'}

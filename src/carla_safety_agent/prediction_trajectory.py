"""Explicit spatial contracts for reviewed local PID telemetry, never inferred timing."""
import hashlib
import inspect
import math
from functools import lru_cache
from .navigation_reference import navigation_diagnostic

SCHEMA='carla-prediction-spatial/2'
PID='4a244e026b41acf0b9d3db3208bf0c15448f976024ebb495a70bdfc05c6eda9c'
CONTROLLERS={'vad':PID,'uniad':PID,'uniad-tiny':PID,'uniad-base':PID,
             'thinktwice':'d4343e889691d61d5521874a312a71775c48a67eacda0c6e8f6a6a5ac2af11c1',
             'driveadapter':'d4343e889691d61d5521874a312a71775c48a67eacda0c6e8f6a6a5ac2af11c1',
             'tcp':'819840cbc5cbbcfdc4a6022705ebad9452ec5eb08c24fdc15c9244f150cc49e7',
             'admlp':'75c5474763d756f4d34f232076656b19ead52edf0ed6c9568848c539c4976e86'}
ALIASES={'driveadapter-experimental':'driveadapter','thinktwice-experimental':'thinktwice','UniADAgent':'uniad','UniadAgent':'uniad','AD-MLP':'admlp','TCP':'tcp','VAD':'vad',
         'UniAD-Tiny':'uniad-tiny','UniAD-Base':'uniad-base'}
ORIGINAL_MODELS = ('thinktwice', 'driveadapter')
HEADING_MODELS = ('tcp', 'admlp', *ORIGINAL_MODELS)


@lru_cache(maxsize=32)
def controller_digest(function):
    source=inspect.getsource(function).rstrip('\n')+'\n'
    return hashlib.sha256(source.encode()).hexdigest()


def raw_points(metadata,model):
    outputs=metadata.get('planning_outputs')
    if not isinstance(outputs,dict):raise ValueError('No controller telemetry')
    if model in HEADING_MODELS:
        points=[outputs.get('wp_'+str(i)) for i in range(1,5)]
    else:
        points=outputs.get('plan')
    if not isinstance(points,list) or not 1<=len(points)<=1000:
        raise ValueError('Prediction point count unavailable or out of bounds')
    width=3 if model=='admlp' else 2
    if any(not isinstance(point,(list,tuple)) or len(point)!=width or
           any(type(value) not in (int,float) or not math.isfinite(value) or abs(value)>10000 for value in point)
           for point in points):
        raise ValueError('Prediction components do not match the reviewed model output layout')
    return [[float(value) for value in (point[:2][::-1] if model in ORIGINAL_MODELS else point[:2])] for point in points]


def spatial_contract(model,digest):
    return {'schema_version':SCHEMA,'model':model,'controller_sha256':digest,
            'raw_axes':'forward_right' if model in ORIGINAL_MODELS else 'right_forward','unit':'m',
            'ignored_for_spatial_plot':['relative_heading_rad'] if model=='admlp' else [],
            'reference':'ego_heading' if model in HEADING_MODELS else 'virtual_lidar',
            'reference_offset_body_m':[0.,0.,0.] if model in HEADING_MODELS else [-.39,0.,1.84],
            'telemetry_field':'planning_outputs',
            'point_dt_s':None}


def capture_prediction(agent,metadata):
    if metadata.get('source')!='model-input':
        return {'state':'unavailable','reason':'No model prediction in standalone capture'}
    model=ALIASES.get(metadata.get('model'),metadata.get('model'))
    if model not in CONTROLLERS:
        return {'state':'unavailable','reason':'Model coordinate contract not reviewed'}
    try:
        owner=getattr(agent,'net',None) if model in ('tcp','admlp') else getattr(agent,'pidcontroller',None)
        if model in ORIGINAL_MODELS:owner=getattr(agent,'model',None)
        method=getattr(owner,'control_pid',None)
        digest=controller_digest(getattr(method,'__func__',method))
        if digest!=CONTROLLERS[model]:raise ValueError('Controller source differs from reviewed coordinate contract')
        if model not in HEADING_MODELS:
            import numpy as np
            actual=np.asarray(getattr(agent,'lidar2ego',None),dtype=float)
            expected=np.array([[0,1,0,-.39],[-1,0,0,0],[0,0,1,1.84],[0,0,0,1]])
            if actual.shape!=(4,4) or not np.allclose(actual,expected,rtol=0,atol=1e-8):
                raise ValueError('Virtual LiDAR reference calibration differs from reviewed contract')
        if metadata.get('planning_anchor') is None:
            step,history=metadata.get('model_step'),metadata.get('planning_warmup_steps')
            if (model in HEADING_MODELS and type(step) is int and type(history) is int and 0<=step<history and
                    metadata.get('planning_observed_calls')==0):
                return {'state':'warmup','reason':'Model has not emitted a planning output during history warm-up',
                        'model_step':step,'required_history_steps':history}
            raise ValueError('No observed planning origin; stale telemetry is not assumed fresh')
        return {'state':'available','contract':spatial_contract(model,digest),
                'right_forward_m':raw_points(metadata,model),'anchor':metadata['planning_anchor'],'timing_verified':False}
    except (TypeError,OSError,ValueError,AttributeError) as exc:
        return {'state':'unavailable','reason':str(exc)}


def replay_prediction(metadata,pose):
    """Express a heading-plane prediction in the same body frame as recorded poses."""
    import numpy as np
    unavailable=lambda reason:{'state':'unavailable','reason':reason,'points':[],
                               'timing_verified':False,'error_metrics_computed':False}
    saved=metadata.get('prediction')
    if not isinstance(saved,dict):return unavailable('Legacy data has no explicit prediction coordinate contract')
    if saved.get('state')!='available':
        result=unavailable(str(saved.get('reason','Prediction unavailable')))
        result['source_state']=saved.get('state')
        return result
    try:
        contract=saved.get('contract')
        model=ALIASES.get(metadata.get('model'),metadata.get('model'))
        if (metadata.get('source')!='model-input' or model not in CONTROLLERS or
                contract!=spatial_contract(model,CONTROLLERS[model]) or saved.get('timing_verified') is not False):
            raise ValueError('Prediction coordinate contract mismatch')
        raw=raw_points(metadata,model)
        if saved.get('right_forward_m')!=raw:raise ValueError('Prediction does not match saved controller output')
        anchor=saved.get('anchor')
        if not isinstance(anchor,dict) or anchor!=metadata.get('planning_anchor'):
            raise ValueError('Prediction origin does not match observed planning call')
        if (type(anchor.get('frame')) is not int or type(metadata.get('frame')) is not int or
                anchor['frame']>metadata['frame'] or type(anchor.get('model_step')) is not int or
                type(metadata.get('model_step')) is not int or anchor['model_step']>metadata['model_step']):
            raise ValueError('Invalid prediction source frame or step')
        if any(type(value) not in (int,float) or not math.isfinite(value) for value in (anchor.get('timestamp'),metadata.get('timestamp'))):
            raise ValueError('Invalid prediction timestamp')
        age=metadata['timestamp']-anchor['timestamp']
        if not 0<=age<=30:raise ValueError('Prediction source is in the future or older than 30 seconds')
        pose=np.asarray(pose,dtype=float)
        origin=np.asarray(anchor.get('ego_matrix'),dtype=float)
        for matrix in (pose,origin):
            if (matrix.shape!=(4,4) or not np.isfinite(matrix).all() or
                    not np.allclose(matrix[3],[0,0,0,1]) or
                    not np.allclose(matrix[:3,:3].T@matrix[:3,:3],np.eye(3),atol=1e-5) or
                    not np.isclose(np.linalg.det(matrix[:3,:3]),1,atol=1e-5)):
                raise ValueError('Prediction requires rigid current and source ego poses')
        inverse=np.linalg.inv(pose)
        forward=origin[:2,0];length=float(np.linalg.norm(forward))
        if length<1e-6:raise ValueError('Vertical ego heading is not supported')
        forward=forward/length;right=np.array([-forward[1],forward[0]])
        points=[]
        for i,(r,f) in enumerate(raw):
            if contract['reference']=='virtual_lidar':
                xyz=(inverse@origin@np.array([f-.39,r,1.84,1.]))[:3]
            else:
                offset=np.array([*(forward*f+right*r),0.])
                xyz=(inverse@np.array([*(origin[:3,3]+offset),1.]))[:3]
            points.append({'step':i+1,'dt_s':None,'xyz_m':xyz.tolist()})
        return {'state':'available','points':points,'contract':contract,'timing_verified':False,
                'source_frame':anchor['frame'],'source_model_step':anchor['model_step'],
                'prediction_age_s':age,'reused':anchor['frame']!=metadata['frame'],
                'navigation_diagnostic':navigation_diagnostic(anchor,origin) if model=='driveadapter' else None,
                'reference_warning':('DriveAdapter 使用运动补偿和平滑后的 GPS 导航位置；当前叠加使用 CARLA 真实车辆位姿，两者的精确一致性尚未验证，不能用于精确轨迹误差评估。'
                                     if model=='driveadapter' else None),
                'error_metrics_computed':False,'source':'saved_controller_prediction',
                'note':'Spatial overlay only; prediction point timing and future error are not verified'}
    except (ValueError,TypeError,KeyError) as exc:
        return unavailable(str(exc))

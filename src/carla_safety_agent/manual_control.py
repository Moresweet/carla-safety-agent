"""Bounded, session-scoped manual controls with a dead-man brake."""
import math

SAFE_CONTROL={'throttle':0.0,'steer':0.0,'brake':1.0,'hand_brake':True,'reverse':False}


def validate_control(data):
    if not isinstance(data,dict): raise ValueError('Control must be an object')
    result={}
    for key,low,high in (('throttle',0,1),('brake',0,1),('steer',-1,1)):
        value=data.get(key,0)
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not low<=value<=high:
            raise ValueError(f'Invalid {key}')
        result[key]=float(value)
    for key in ('hand_brake','reverse'):
        value=data.get(key,False)
        if not isinstance(value,bool): raise ValueError(f'Invalid {key}')
        result[key]=value
    return result


def current_control(command, execution_id, now):
    """Commands expire after 0.5 s wall-monotonic time, even if simulation stalls."""
    if not isinstance(command,dict) or command.get('execution_id')!=execution_id:
        return dict(SAFE_CONTROL)
    issued=command.get('issued_monotonic')
    if isinstance(issued,bool) or not isinstance(issued,(int,float)) or not math.isfinite(issued) or not 0<=now-issued<=.5:
        return dict(SAFE_CONTROL)
    try: return validate_control(command['control'])
    except (KeyError,ValueError,TypeError,AttributeError): return dict(SAFE_CONTROL)

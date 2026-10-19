"""Read only execution-bound worker failures; old reports are not evidence."""
from .scene_store import read_json


def capture_failure(path,execution_id):
    if not isinstance(execution_id,str) or not execution_id:return None
    try:row=read_json(path,max_bytes=64*1024)
    except (OSError,ValueError):return None
    if not isinstance(row,dict) or row.get('execution_id')!=execution_id or row.get('source')!='sensor-rig':return None
    error=row.get('error')
    if not isinstance(error,str) or not error.strip():return None
    categories = {'capture_io_error': 'capture_io_error', 'quota_unknown': 'capture_quota_unknown'}
    return {'error':error[:2000], 'category':categories.get(row.get('stop_reason'), 'capture_worker')
            if isinstance(row.get('stop_reason'), str) else 'capture_worker'}

"""Bounded native-map isolation for replay. No live-world fallback."""
import json
import math
import os
import subprocess
import sys
import threading
from .map_projection_archive import read_map_projection

_lock=threading.Lock()


def archived_prediction(root, manifest, metadata, pose):
    def unavailable(reason):return {'state':'unavailable','reason':reason,'points':[]}
    reference=manifest.get('map_projection')
    if not isinstance(reference,dict) or reference.get('state')!='available':
        return unavailable('Recording has no archived map projection; current map is not used')
    if reference.get('map_name')!=manifest.get('map'):
        return unavailable('Recording and archived map identities differ')
    if not _lock.acquire(blocking=False):return unavailable('Offline projection busy; retry this frame')
    try:
        read_map_projection(root,reference)
        request=json.dumps({'root':str(root),'reference':reference,'metadata':metadata,
                            'pose':pose.tolist()},allow_nan=False)
        if len(request.encode())>=4*1024**2:raise ValueError('Projection request exceeds limit')
        result=subprocess.run([sys.executable,'-m','carla_safety_agent.offline_projection_worker'],
            input=request,text=True,capture_output=True,timeout=15,
            env={**os.environ,'PYTHONPATH':os.pathsep.join(sys.path)})
        if result.returncode!=0:return unavailable('Offline projection worker failed; no live-map substitution')
        if len(result.stdout)>256*1024:raise ValueError('Projection response exceeds limit')
        value=json.loads(result.stdout)
        if (not isinstance(value,dict) or value.get('state')!='available' or
                value.get('map_sha256')!=reference['sha256'] or
                value.get('source_frame')!=(metadata.get('planning_anchor') or {}).get('frame') or
                value.get('timing_verified') is not False or value.get('error_metrics_computed') is not False):
            raise ValueError('Invalid offline projection response')
        points=value.get('points')
        if not isinstance(points,list) or len(points)!=4:raise ValueError('Expected four projected points')
        for i,point in enumerate(points):
            if not isinstance(point,dict) or point.get('step')!=i+1 or point.get('dt_s') is not None:
                raise ValueError('Invalid projected point identity')
            xyz=point.get('xyz_m')
            if not isinstance(xyz,list) or len(xyz)!=3 or any(type(x) not in (int,float) or not math.isfinite(x) for x in xyz):
                raise ValueError('Invalid projected coordinates')
        return value
    except (ValueError,OSError,subprocess.TimeoutExpired) as error:
        return unavailable(str(error))
    finally:_lock.release()

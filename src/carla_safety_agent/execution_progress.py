"""Advisory native-worker stages, never a replacement for session ownership."""
import os
from pathlib import Path
import time

from .scene_store import atomic,finite_number,identifier,read_json
from .session import observed_process_identity

PHASES={'connecting','loading_world','spawning','loading_model','warming_sensors',
        'inference','preview','cleaning','worker_finished'}


def progress_path(root,run_id):
    root=Path(root)
    identifier(run_id)
    path=root/'experiments'/run_id/'progress.json'
    if any(p.is_symlink() for p in (root,root/'experiments',path.parent,path)):
        raise ValueError('Linked progress path refused')
    return path


def validate_progress(row):
    required={'schema_version','run_id','owner','phase','updated_at','completed_steps','total_steps','preview_until'}
    if not isinstance(row,dict) or set(row)!=required or row['schema_version']!='carla-execution-progress/1':
        raise ValueError('Invalid execution progress schema')
    identifier(row['run_id'])
    owner=row['owner']
    if (not isinstance(owner,dict) or set(owner)!={'pid','start_ticks'} or type(owner['pid']) is not int
        or owner['pid']<=0 or not isinstance(owner['start_ticks'],str) or not owner['start_ticks'].isdigit()):
        raise ValueError('Invalid execution progress owner')
    if row['phase'] not in PHASES or not finite_number(row['updated_at']) or row['updated_at']<0:
        raise ValueError('Invalid execution progress stage or timestamp')
    done,total=row['completed_steps'],row['total_steps']
    if (done is None)!=(total is None) or (done is not None and
        (type(done) is not int or type(total) is not int or not 0<=done<=total<=1000000 or total==0)):
        raise ValueError('Invalid execution step counts')
    until=row['preview_until']
    if until is not None and (row['phase']!='preview' or not finite_number(until) or
                              not row['updated_at']<=until<=row['updated_at']+3600):
        raise ValueError('Invalid execution preview deadline')
    return row


class ExecutionProgress:
    def __init__(self,root,run_id,owner,clock=time.time):
        self.path=progress_path(root,run_id);self.run_id=run_id;self.owner=owner
        self.clock=clock;self.disabled=False

    def emit(self,phase,*,completed_steps=None,total_steps=None,preview_seconds=None):
        if self.disabled:return
        try:
            now=self.clock()
            row={'schema_version':'carla-execution-progress/1','run_id':self.run_id,'owner':self.owner,
                'phase':phase,'updated_at':now,'completed_steps':completed_steps,'total_steps':total_steps,
                'preview_until':None if preview_seconds is None else now+preview_seconds}
            validate_progress(row)
            # Session.begin already created this exact execution directory.
            atomic(self.path,row)
        except Exception as exc:
            self.disabled=True
            print(f'Execution progress unavailable (simulation continues): {exc}',flush=True)


def progress_from_environment():
    root=os.environ.get('CSA_RESOURCE_DATA_ROOT');run_id=os.environ.get('CSA_EXECUTION_ID')
    if root is None or run_id is None:return None
    try:return ExecutionProgress(root,run_id,observed_process_identity(os.getpid()))
    except Exception as exc:
        print(f'Execution progress unavailable: {exc}',flush=True)
        return None


def read_progress(root,session,now=None):
    """Read the selected execution only; old stages never declare completion."""
    run_id=session.get('run_id')
    if not run_id:return {'available':False,'reason':'No selected execution'}
    try:
        row=validate_progress(read_json(progress_path(root,run_id),max_bytes=64*1024))
        if row['run_id']!=run_id or row['owner']!=session.get('process'):
            raise ValueError('Progress belongs to another execution owner')
        now=time.time() if now is None else now
        age=now-row['updated_at']
        if age < -5:raise ValueError('Progress timestamp is in the future')
        active=session.get('state') in ('preparing','running','stopping','recovering')
        return {'available':True,**row,'age_s':max(0,age),'active':active,
            'preview_remaining_s':max(0,row['preview_until']-now) if active and row['preview_until'] is not None else None,
            'scope':'Last worker report, not a heartbeat, timeout diagnosis or completion certificate'}
    except FileNotFoundError:return {'available':False,'reason':'This execution has not reported stages'}
    except (ValueError,OSError,TypeError) as exc:return {'available':False,'invalid':True,'reason':str(exc)}

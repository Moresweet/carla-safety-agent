"""Local execution provenance, separate from recording completion status."""
from pathlib import Path
from .scene_store import identifier, read_json


def execution_summary(experiments, execution_id):
    try:
        key = identifier(execution_id)
        root = Path(experiments)
        folder = root/key
        if root.is_symlink() or folder.is_symlink():
            raise ValueError('Linked execution directory refused')
        record = read_json(folder/'execution.json', max_bytes=8*1024**2)
        if not isinstance(record, dict) or record.get('run_id') != key:
            raise ValueError('Execution identity mismatch')
        state = record.get('state')
        if state not in ('idle','preparing','running','stopping','recovering','completed','stopped','failed'):
            raise ValueError('Unknown execution state')
        error = record.get('error')
        if error is not None and not isinstance(error, str):
            raise ValueError('Invalid execution error')
        return {'available':True,'execution_id':key,'state':state,'error':error,
                'scope':'Saved local execution record; not live process status or driving-quality verdict'}
    except (ValueError, OSError) as error:
        return {'available':False,'message':str(error)}

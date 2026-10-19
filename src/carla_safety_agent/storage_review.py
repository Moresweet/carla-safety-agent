"""Read-only storage review for the studio; no deletion eligibility decisions."""
from pathlib import Path
import shutil
import threading
from .capture_storage import inventory_captures
from .capture_retention import CaptureRetention
from .capture_references import capture_references, queue_references, project_references
from .split_registry import registered_split_references


_review_lock = threading.Lock()


class StorageReviewBusy(ValueError):
    pass


def storage_review(root, data_root):
    if not _review_lock.acquire(blocking=False):
        raise StorageReviewBusy('Storage scan already running; retry explicitly after it finishes')
    try:
        return _storage_review(root, data_root)
    finally:
        _review_lock.release()


def _storage_review(root, data_root):
    marker = CaptureRetention(data_root,root).snapshot()
    result = inventory_captures(root)
    derived = capture_references(root)
    queues = queue_references(Path(data_root)/'experiment-queues')
    projects = project_references(Path(data_root)/'project-bundles')
    splits = registered_split_references(Path(data_root)/'dataset-splits')
    for row in result['recordings']:
        row['keep_reason'] = marker['records'].get(row['directory'],{}).get('reason')
        row['derived_referenced_by'] = derived['references'].get(row['directory'],[])
        row['project_referenced_by'] = projects['references'].get(row['directory'],[])
        row['split_referenced_by'] = splits['references'].get(row['directory'],[])
        execution = row.get('execution_id')
        row['queue_referenced_by'] = queues['references'].get(execution,[]) if isinstance(execution,str) else []
    result['recordings'].sort(key=lambda row:row['allocated_bytes'],reverse=True)
    result['complete'] = result['complete'] and derived['complete'] and queues['complete'] and projects['complete'] and splits['complete']
    result['warnings'].extend(derived['warnings']+queues['warnings']+projects['warnings']+splits['warnings'])
    result['registered_split_references'] = splits
    result['project_references'] = projects
    result['retention_revision'] = marker['revision']
    # A simultaneous marker change invalidates the combined review.
    if CaptureRetention(data_root,root).snapshot()['revision'] != marker['revision']:
        result['complete'] = False
        result['warnings'].append('Retention changed during review; refresh required')
    result['free_bytes'] = shutil.disk_usage(root).free
    result['limitations'].append('Local validated project JSON and registered splits scanned; other external references and unregistered splits not scanned; unmarked/unreferenced does not mean deletable')
    return result

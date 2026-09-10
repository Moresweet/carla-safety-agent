"""Path-confined local batch catalog for UI/API consumers."""
import uuid
from pathlib import Path
from .scene_store import identifier
from .experiment_matrix import compile_matrix
from .experiment_queue import ExperimentQueue
from .experiment_report import summarize_queue


class BatchCatalog:
    def __init__(self, root):
        self.root = Path(root).resolve()

    def directory(self, batch_id):
        identifier(batch_id)
        path = self.root/batch_id
        if path.is_symlink() or path.resolve().parent != self.root or not path.is_dir():
            raise ValueError('Unknown batch')
        return path

    def read(self, batch_id):
        path = self.directory(batch_id)/'queue.json'
        if path.is_symlink() or path.stat().st_size > 32*1024*1024:
            raise ValueError('Invalid batch state path or size')
        state = ExperimentQueue(self.directory(batch_id)).read()
        summarize_queue(state)  # Verify plan identity and job/attempt association.
        return state

    def create(self, dimensions):
        compile_matrix(dimensions)  # Reject before making a directory.
        batch_id = uuid.uuid4().hex
        state = ExperimentQueue(self.root/batch_id).create(dimensions)
        return {'batch_id': batch_id, 'report': summarize_queue(state), 'dispatched': False}

    def list(self, limit=30, after=None):
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError('Batch page limit must be 1..100')
        if after is not None:
            identifier(after)
        names = sorted(p.name for p in self.root.iterdir() if p.is_dir()) if self.root.exists() else []
        names = [n for n in names if after is None or n > after]
        batches = []
        for name in names[:limit]:
            try:
                report = summarize_queue(self.read(name))
                batches.append({'batch_id': name, 'job_count': report['job_count'],
                    'paused': report['paused'], 'state_counts': report['state_counts']})
            except (ValueError, KeyError, TypeError, OSError) as exc:
                batches.append({'batch_id': name, 'error': str(exc)})
        return {'batches': batches, 'next_cursor': names[limit-1] if len(names)>limit else None}

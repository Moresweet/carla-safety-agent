"""One background dataset scan at a time, with saved, explicitly dated evidence."""
import hashlib
import json
from pathlib import Path
import threading
import uuid

from .capture_quality import audit_capture
from .replay import dataset_path


class QualityService:
    def __init__(self, datasets, reports, validator, python):
        self.datasets, self.reports = Path(datasets), Path(reports)
        self.validator, self.python = validator, python
        self.lock = threading.RLock()
        self.active = None
        self.transient = {}

    def _report_path(self, run_id):
        # Never use a user-supplied path as a report filename.
        return self.reports / (hashlib.sha256(run_id.encode()).hexdigest() + '.json')

    def status(self, run_id):
        dataset_path(self.datasets, run_id)
        with self.lock:
            if run_id in self.transient:
                return dict(self.transient[run_id])
            path = self._report_path(run_id)
            if path.exists():
                result = json.loads(path.read_text())
                if result.get('run_id') != run_id:
                    raise ValueError('Quality report identity mismatch')
                return result
            return {'run_id': run_id, 'state': 'not_checked'}

    def start(self, run_id):
        if not isinstance(run_id, str) or not run_id:
            raise ValueError('Dataset run_id is required')
        path = dataset_path(self.datasets, run_id)
        manifest = json.loads((path / 'manifest.json').read_text())
        if manifest.get('run_id') != run_id:
            raise ValueError('Dataset identity mismatch')
        if manifest.get('status') not in ('saved', 'saved_limit', 'saved_cleanup_error'):
            raise ValueError('Only saved captures can be audited')
        if manifest.get('schema_version') != 'carla-safety-dataset/0.2':
            raise ValueError('Legacy captures do not contain the unified sensor contract')
        with self.lock:
            if self.active is not None:
                raise ValueError('A dataset quality scan is already running')
            self.active = run_id
            self.transient[run_id] = {'run_id': run_id, 'state': 'running'}
            try:
                threading.Thread(target=self._scan, args=(run_id, path), daemon=True).start()
            except Exception:
                self.active = None
                self.transient.pop(run_id, None)
                raise
            return {'run_id': run_id, 'state': 'running'}

    def _scan(self, run_id, path):
        try:
            before = (path / 'manifest.json').read_bytes()
            report = audit_capture(path, self.validator, self.python)
            if (path / 'manifest.json').read_bytes() != before:
                report.update(state='incomplete', detail='Dataset manifest changed during validation')
            report.update(run_id=run_id, manifest_sha256=hashlib.sha256(before).hexdigest())
            self.reports.mkdir(parents=True, exist_ok=True)
            temporary = self.reports / (uuid.uuid4().hex + '.tmp')
            temporary.write_text(json.dumps(report, ensure_ascii=False))
            temporary.replace(self._report_path(run_id))
        except Exception as error:
            report = {'run_id': run_id, 'state': 'incomplete', 'detail': str(error)}
        finally:
            with self.lock:
                self.transient[run_id] = report
                self.active = None

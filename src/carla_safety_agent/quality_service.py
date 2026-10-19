"""One background dataset scan at a time, with saved, explicitly dated evidence."""
import hashlib
import json
from pathlib import Path
import threading
import uuid
import time
import fcntl
from .owned_resources import durable_write

from .capture_quality import audit_capture
from .replay import dataset_path


class QualityService:
    def __init__(self, datasets, reports, validator, python):
        self.datasets, self.reports = Path(datasets), Path(reports)
        self.validator, self.python = validator, python
        self.lock = threading.RLock()
        self.active = None
        self.transient = {}
        self._lease = None

    def _report_path(self, run_id):
        # Never use a user-supplied path as a report filename.
        return self.reports / (hashlib.sha256(run_id.encode()).hexdigest() + '.json')

    def status(self, run_id):
        dataset = dataset_path(self.datasets, run_id)
        def observed(result):
            result = dict(result)
            expected = result.get('manifest_sha256')
            if isinstance(expected, str) and len(expected) == 64 and all(c in '0123456789abcdef' for c in expected):
                try:
                    current = hashlib.sha256((dataset / 'manifest.json').read_bytes()).hexdigest()
                    result['manifest_freshness'] = 'unchanged' if current == expected else 'changed'
                except OSError:
                    result['manifest_freshness'] = 'unknown'
            else:
                result['manifest_freshness'] = 'unknown'
            return result
        with self.lock:
            if run_id in self.transient:
                return observed(self.transient[run_id])
            path = self._report_path(run_id)
            if path.exists():
                result = json.loads(path.read_text())
                if result.get('run_id') != run_id:
                    raise ValueError('Quality report identity mismatch')
                if result.get('state') == 'running':
                    result = {**result, 'state':'incomplete', 'reason_code':'validation_interrupted',
                              'detail':'Saved quality task is not managed by this service instance; completion is unknown. No automatic retry.'}
                return observed(result)
            return {'run_id': run_id, 'state': 'not_checked'}

    def start(self, run_id):
        if not isinstance(run_id, str) or not run_id:
            raise ValueError('Dataset run_id is required')
        path = dataset_path(self.datasets, run_id)
        manifest = json.loads((path / 'manifest.json').read_text())
        if manifest.get('run_id') != run_id:
            raise ValueError('Dataset identity mismatch')
        if manifest.get('status') not in ('saved', 'saved_limit', 'saved_cleanup_error', 'saved_capture_error', 'saved_recovered', 'saved_excerpt'):
            raise ValueError('Only saved captures can be audited')
        if manifest.get('schema_version') != 'carla-safety-dataset/0.2':
            raise ValueError('Legacy captures do not contain the unified sensor contract')
        with self.lock:
            if self.active is not None:
                raise ValueError('A dataset quality scan is already running')
            self.reports.mkdir(parents=True, exist_ok=True)
            lease = (self.reports / 'scan.lock').open('a')
            try:
                fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                lease.close()
                raise ValueError('Another quality worker holds the scan lock') from exc
            self._lease = lease
            try:
                return self._start_admitted(run_id)
            except BaseException:
                self._lease = None
                lease.close()
                raise

    def _start_admitted(self, run_id):
        path = dataset_path(self.datasets, run_id)
        previous = self._report_path(run_id)
        if previous.exists():
            old = json.loads(previous.read_text())
            if old.get('run_id') != run_id:
                raise ValueError('Quality report identity mismatch')
            history = self.reports / 'history'
            history.mkdir(exist_ok=True)
            durable_write(history / (uuid.uuid4().hex + '.json'), old, exclusive=True)
        pending = {'run_id':run_id, 'state':'running', 'started_at_unix':time.time()}
        durable_write(previous, pending)
        self.active = run_id
        self.transient[run_id] = pending
        try:
            threading.Thread(target=self._scan, args=(run_id, path), daemon=True).start()
        except Exception:
            self.active = None
            self.transient.pop(run_id, None)
            raise
        return {'run_id': run_id, 'state': 'running'}

    def _scan(self, run_id, path):
        published = False
        try:
            before = (path / 'manifest.json').read_bytes()
            options = {'pass_fds': (self._lease.fileno(),)} if self._lease is not None else {}
            report = audit_capture(path, self.validator, self.python, **options)
            if (path / 'manifest.json').read_bytes() != before:
                report.update(state='incomplete', detail='Dataset manifest changed during validation')
            report.update(run_id=run_id, manifest_sha256=hashlib.sha256(before).hexdigest())
            self.reports.mkdir(parents=True, exist_ok=True)
            durable_write(self._report_path(run_id), report)
            published = True
        except Exception as error:
            report = {'run_id': run_id, 'state': 'incomplete', 'detail': str(error)}
        finally:
            with self.lock:
                if published:
                    # Terminal disk evidence may later be superseded by another
                    # service instance; do not permanently mask it with a cache.
                    self.transient.pop(run_id, None)
                else:
                    self.transient[run_id] = report
                self.active = None
                if self._lease is not None:
                    self._lease.close()
                    self._lease = None

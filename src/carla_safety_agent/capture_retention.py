"""Explicit durable keep markers. Absence is NOT permission to delete."""
import fcntl
import os
from pathlib import Path

from .scene_store import atomic, identifier, read_json


class CaptureRetention:
    def __init__(self, data_root, capture_root):
        self.root = Path(data_root)
        self.capture_root = Path(capture_root)
        self.path = self.root/'capture-retention.json'

    def snapshot(self):
        if not self.path.exists() and not self.path.is_symlink():
            return {'schema_version':'capture-retention/1', 'revision':0, 'records':{}}
        doc = read_json(self.path)
        if (not isinstance(doc, dict) or doc.get('schema_version') != 'capture-retention/1'
                or type(doc.get('revision')) is not int or doc['revision'] < 0
                or not isinstance(doc.get('records'), dict)):
            raise ValueError('Invalid capture retention state; protection unknown')
        for run_id, record in doc['records'].items():
            identifier(run_id)
            if (not isinstance(record, dict) or set(record) != {'reason'}
                    or not isinstance(record['reason'], str) or not 1 <= len(record['reason']) <= 500):
                raise ValueError('Invalid keep marker; protection unknown')
        return doc

    def set_keep(self, run_id, keep, reason, *, expected_revision):
        identifier(run_id)
        if type(keep) is not bool or type(expected_revision) is not int or expected_revision < 0:
            raise ValueError('Invalid keep flag or revision')
        if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 500:
            raise ValueError('A reason of 1..500 characters is required')
        if self.root.is_symlink() or self.capture_root.is_symlink():
            raise ValueError('Linked state/capture root is not supported')
        folder = self.capture_root/run_id
        if keep:
            if folder.is_symlink() or not folder.is_dir():
                raise ValueError('Capture must exist in the configured root')
            manifest = read_json(folder/'manifest.json')
            if not isinstance(manifest, dict) or manifest.get('run_id') != run_id:
                raise ValueError('Capture identity mismatch')
        self.root.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.root/'capture-retention.lock', os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, 'r+') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            doc = self.snapshot()
            if doc['revision'] != expected_revision:
                raise ValueError('Retention revision changed; refresh before editing')
            if keep:
                doc['records'][run_id] = {'reason':reason.strip()}
            else:
                doc['records'].pop(run_id, None)
            doc['revision'] += 1
            atomic(self.path, doc)
            return doc

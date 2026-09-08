"""Durable, identity-checked local execution lifecycle; no CARLA RPCs here."""
import json
import os
import threading
import time
import uuid
from pathlib import Path

ACTIVE = {'preparing', 'running', 'stopping', 'recovering'}


def process_identity(pid):
    """Linux start ticks prevent a stale PID file from signalling another job."""
    try:
        text = Path(f'/proc/{int(pid)}/stat').read_text()
        fields = text[text.rfind(')')+2:].split()
        if fields[0] == 'Z':
            return None
        return {'pid': int(pid), 'start_ticks': fields[19]}
    except (OSError, ValueError, IndexError):
        return None


class SessionJournal:
    def __init__(self, root):
        self.root = Path(root)
        self.lock = threading.RLock()
        self.state = {'state': 'idle', 'run_id': None}
        path = self.root/'session.json'
        if path.exists():
            # Do not silently overwrite a corrupt journal.
            self.state = json.loads(path.read_text())

    def snapshot(self):
        with self.lock:
            return json.loads(json.dumps(self.state))

    def owned_pid(self):
        with self.lock:
            identity = self.state.get('process')
            if identity and process_identity(identity['pid']) == identity:
                return identity['pid']
            return None

    def _save(self):
        self.root.mkdir(parents=True, exist_ok=True)
        self.state['updated_at'] = time.time()
        paths = [self.root/'session.json']
        if self.state.get('run_id'):
            paths.append(self.root/'experiments'/self.state['run_id']/'execution.json')
        for path in paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix('.tmp')
            temporary.write_text(json.dumps(self.state, ensure_ascii=False, indent=2, allow_nan=False))
            temporary.replace(path)

    def begin(self, kind, configuration):
        with self.lock:
            if self.state['state'] in ACTIVE:
                raise RuntimeError('Session must finish recovery before starting another task')
            self.state = {'state': 'preparing', 'run_id': uuid.uuid4().hex,
                          'kind': kind, 'configuration': configuration, 'process': None,
                          'started_at': time.time(), 'ended_at': None, 'error': None}
            self._save()
            return self.state['run_id']

    def transition(self, target, **fields):
        allowed = {
            'preparing': {'running', 'failed', 'recovering'},
            'running': {'stopping', 'recovering', 'failed'},
            'stopping': {'recovering', 'failed'},
            'recovering': {'completed', 'stopped', 'failed'},
        }
        with self.lock:
            current = self.state['state']
            if current != target and target not in allowed.get(current, set()):
                raise RuntimeError(f'Invalid session transition: {current} -> {target}')
            self.state.update(fields, state=target)
            if target not in ACTIVE:
                self.state['ended_at'] = time.time()
            self._save()

    def attach(self, pid):
        # A very short-lived diagnostic may exit before /proc is read.
        self.transition('running', process=process_identity(pid))

    def reconcile(self):
        with self.lock:
            if self.state['state'] in ACTIVE and not self.owned_pid():
                self.transition('recovering', error='Execution owner exited; world recovery required')
            return self.snapshot()

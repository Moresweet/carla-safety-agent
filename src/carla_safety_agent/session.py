"""Durable, identity-checked local execution lifecycle; no CARLA RPCs here."""
import json
import os
import threading
import time
import uuid
from pathlib import Path

ACTIVE = {'preparing', 'running', 'stopping', 'recovering'}


def observed_process_identity(pid):
    """Strict observer: only a missing PID or zombie proves owner absence.

    Permission and malformed-record errors propagate; callers must not interpret
    observation failure as permission to dispatch another simulation.
    """
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        raise ValueError('Invalid process ID')
    try:
        text = Path(f'/proc/{pid}/stat').read_text()
    except FileNotFoundError:
        return None
    boundary = text.rfind(')')
    fields = text[boundary+2:].split()
    if boundary < 0 or len(fields) < 20 or not fields[19].isdigit():
        raise ValueError('Malformed process stat record')
    if fields[0] == 'Z':
        return None
    return {'pid': pid, 'start_ticks': fields[19]}


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

    def read_execution(self, run_id):
        """Read only a bounded local record; never accept arbitrary file paths."""
        from .scene_store import identifier
        run_id = identifier(run_id)
        root = (self.root/'experiments').resolve()
        path = (root/run_id/'execution.json').resolve()
        if path.parent.parent != root or path.parent.name != run_id or path.name != 'execution.json':
            raise ValueError('Execution record outside experiment directory')
        if path.stat().st_size > 8*1024*1024:
            raise ValueError('Oversized execution record')
        result = json.loads(path.read_text())
        if not isinstance(result, dict) or result.get('run_id') != run_id:
            raise ValueError('Execution identity mismatch')
        return result

    def owned_pid(self):
        with self.lock:
            identity = self.state.get('process')
            if identity and process_identity(identity['pid']) == identity:
                return identity['pid']
            return None

    def list_executions(self, limit=50, after=None):
        """Page by immutable run ID; malformed records remain visible as errors."""
        from .scene_store import identifier
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError('Execution page limit must be 1..100')
        if after is not None:
            identifier(after)
        root = self.root/'experiments'
        names = sorted(p.name for p in root.iterdir() if p.is_dir()) if root.exists() else []
        names = [name for name in names if after is None or name > after]
        selected = names[:limit]
        records = []
        for name in selected:
            try:
                item = self.read_execution(name)
                configuration = item.get('configuration') or {}
                request = configuration.get('request') or {}
                if not isinstance(configuration, dict) or not isinstance(request, dict):
                    raise ValueError('Invalid execution configuration')
                records.append({key:item.get(key) for key in
                    ('run_id','kind','state','started_at','ended_at','error','outcome')})
                records[-1].update(algorithm=request.get('algorithm'),
                    has_starting_scene=isinstance(configuration.get('starting_scene'),dict))
            except (ValueError, OSError, AttributeError) as exc:
                records.append({'run_id':name,'record_error':str(exc)})
        return {'executions':records,'next_cursor':selected[-1] if len(names)>limit else None,
                'order':'run_id_ascending'}

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

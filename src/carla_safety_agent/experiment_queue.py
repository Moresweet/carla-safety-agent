"""Process-safe local batch ledger, independent of simulation execution.

Reservations survive restarts and are never automatically reclaimed. A caller
must reconcile the actual session before deciding an attempt has ended.
"""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import time
import uuid

from .experiment_matrix import canonical, compile_matrix


class ExperimentQueue:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def locked(self):
        with (self.root/'queue.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def read(self):
        return json.loads((self.root/'queue.json').read_text())

    def write(self, state):
        temporary = self.root/('queue-'+uuid.uuid4().hex+'.tmp')
        with temporary.open('xb') as stream:
            stream.write(canonical(state)); stream.flush(); os.fsync(stream.fileno())
        temporary.replace(self.root/'queue.json')

    def create(self, dimensions):
        plan = compile_matrix(dimensions)
        digest = hashlib.sha256(canonical(plan)).hexdigest()
        with self.locked():
            if (self.root/'queue.json').exists():
                existing = self.read()
                if existing['plan_sha256'] != digest or existing['plan'] != plan:
                    raise ValueError('Queue already belongs to another plan')
                return existing
            state = {'schema_version': 'carla-experiment-queue/1', 'plan_sha256': digest,
                     'plan': plan, 'jobs': [{'job_id': j['job_id'], 'state': 'pending',
                                            'attempts': []} for j in plan['jobs']]}
            self.write(state)
            return state

    def claim(self):
        with self.locked():
            state = self.read()
            if any(j['state'] in ('reserved', 'running') for j in state['jobs']):
                raise ValueError('An unresolved attempt already owns this queue')
            job = next((j for j in state['jobs'] if j['state'] == 'pending'), None)
            if job is None:
                return None
            attempt = {'attempt_id': uuid.uuid4().hex, 'state': 'reserved',
                       'created_at': time.time(), 'execution_id': None}
            job['attempts'].append(attempt); job['state'] = 'reserved'
            self.write(state)
            configuration = next(j['configuration'] for j in state['plan']['jobs'] if j['job_id'] == job['job_id'])
            return {'job_id': job['job_id'], 'attempt': attempt, 'configuration': configuration}

    def update_attempt(self, job_id, attempt_id, *, execution_id=None, outcome=None, result=None):
        with self.locked():
            state = self.read()
            job = next((j for j in state['jobs'] if j['job_id'] == job_id), None)
            if not job or not job['attempts'] or job['attempts'][-1]['attempt_id'] != attempt_id:
                raise ValueError('Stale or unknown queue attempt')
            attempt = job['attempts'][-1]
            if job['state'] not in ('reserved', 'running'):
                raise ValueError('Attempt is already terminal')
            if outcome is None:
                if job['state'] != 'reserved' or not isinstance(execution_id, str) or not execution_id:
                    raise ValueError('Only reserved attempts can bind an execution')
                attempt['execution_id'] = execution_id
                attempt['state'] = job['state'] = 'running'
            else:
                if outcome not in ('completed', 'failed', 'stopped') or not isinstance(result, dict):
                    raise ValueError('Terminal attempt requires outcome and result evidence')
                if execution_id != attempt['execution_id']:
                    raise ValueError('Execution identity mismatch')
                if outcome == 'completed' and job['state'] != 'running':
                    raise ValueError('Unstarted attempt cannot complete')
                attempt.update(state=outcome, ended_at=time.time(), result=result)
                job['state'] = outcome
            self.write(state)
            return attempt

    def retry(self, job_id):
        with self.locked():
            state = self.read()
            job = next((j for j in state['jobs'] if j['job_id'] == job_id), None)
            if not job or job['state'] not in ('failed', 'stopped'):
                raise ValueError('Only failed or stopped jobs can be retried')
            if len(job['attempts']) >= 20:
                raise ValueError('Attempt limit reached')
            job['state'] = 'pending'
            self.write(state)

    def reconcile(self, job_id, attempt_id, journal):
        """Accept only a bound, terminal journal record with no live owner.

        This does not launch work or infer simulator recovery from PID absence.
        The session must already have completed its own recovery lifecycle.
        """
        from .session import process_identity
        with self.locked():
            state = self.read()
            job = next((j for j in state['jobs'] if j['job_id'] == job_id), None)
            if not job or not job['attempts']:
                raise ValueError('Unknown queue job')
            attempt = job['attempts'][-1]
            if attempt['attempt_id'] != attempt_id or job['state'] != 'running':
                raise ValueError('Only the current running attempt can reconcile')
            execution = journal.read_execution(attempt['execution_id'])
            if execution.get('run_id') != attempt['execution_id']:
                raise ValueError('Execution identity mismatch')
            terminal = execution.get('state')
            if terminal not in ('completed', 'failed', 'stopped'):
                return {'reconciled': False, 'state': terminal}
            identity = execution.get('process')
            if identity and process_identity(identity['pid']) == identity:
                return {'reconciled': False, 'state': 'process_still_alive'}
            if execution.get('ended_at') is None:
                raise ValueError('Terminal execution has no end timestamp')
            if terminal == 'completed' and (execution.get('error') or execution.get('returncode') != 0):
                raise ValueError('Completed execution has inconsistent exit evidence')
            result = {'execution': execution, 'source': 'session_journal',
                      'benchmark_passed': None}
            # Execution completion is not a claim of safe driving performance.
            outcome = execution.get('outcome') or {}
            if outcome.get('benchmark_failed') is True:
                result['benchmark_passed'] = False
            attempt.update(state=terminal, ended_at=time.time(), result=result)
            job['state'] = terminal
            self.write(state)
            return {'reconciled': True, 'state': terminal}

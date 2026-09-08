"""Bridge-owned serial scheduler; browser lifecycle never owns the worker."""
import copy
import threading
import time
from .batch_runner import run_batch
from .scene_store import identifier


class BatchService:
    def __init__(self, step, interval=1):
        self.step = step
        self.interval = interval
        self.lock = threading.RLock()
        self.worker = None
        self.cancelled = threading.Event()
        self.record = {'state': 'idle', 'batch_id': None}

    def status(self):
        with self.lock:
            return copy.deepcopy(self.record)

    def start(self, batch_id):
        identifier(batch_id)
        with self.lock:
            if self.worker is not None and self.worker.is_alive():
                raise ValueError('A batch scheduler is already active')
            self.cancelled = threading.Event()
            self.record = {'state': 'running', 'batch_id': batch_id,
                           'started_at': time.time(), 'last_step': None}
            self.worker = threading.Thread(target=self._run, args=(batch_id,), daemon=True)
            self.worker.start()
            return copy.deepcopy(self.record)

    def cancel(self, batch_id):
        with self.lock:
            if self.record['batch_id'] != batch_id:
                raise ValueError('Scheduler batch ownership changed')
            if self.worker is not None and self.worker.is_alive():
                self.cancelled.set()
                self.record['cancel_requested'] = True
            return copy.deepcopy(self.record)

    def _observe(self, result):
        with self.lock:
            self.record['last_step'] = copy.deepcopy(result)

    def _run(self, batch_id):
        try:
            result = run_batch(lambda: self.step(batch_id),
                               lambda: self.cancelled.wait(self.interval),
                               cancelled=self.cancelled.is_set, observe=self._observe)
        except Exception as exc:
            result = {'state': 'needs_attention', 'error': str(exc)}
        with self.lock:
            self.record.update(result, ended_at=time.time())

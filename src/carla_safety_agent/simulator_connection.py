"""Transport and isolated readiness guards before entering native CARLA RPCs.

The local CARLA Python binding can retain the GIL during get_world's timeout.
A refused connection must not freeze unrelated offline dataset HTTP requests.
An open port alone is insufficient, so native readiness is read in a child.
Neither check guarantees that a later world RPC will complete or not crash.
"""
import socket
import json
import os
import subprocess
import sys
import threading
import time


def require_simulator_listener(host: str, port: int) -> None:
    try:
        with socket.create_connection((host, port), timeout=0.25):
            pass
    except OSError as exc:
        raise RuntimeError(
            f"CARLA transport unavailable at {host}:{port}; start the simulator. "
            "Saved datasets remain available for offline replay."
        ) from exc


class SimulatorConnectionProbe:
    """Bounded native readiness read in a disposable process, never a world tick.

    Short positive caching avoids forking for every editor request. Negative
    caching prevents an offline simulator causing a process/request storm.
    This guards entry; it cannot prevent a server dying after the probe.
    """

    def __init__(self, *, runner=subprocess.run, clock=time.monotonic):
        self._runner = runner
        self._clock = clock
        self._lock = threading.Lock()
        self._cache = {}

    def require(self, host: str, port: int) -> None:
        with self._lock:
            key = (host, port)
            cached = self._cache.get(key)
            if cached and self._clock() < cached[0]:
                if cached[1]:
                    raise RuntimeError(cached[1])
                return
            try:
                require_simulator_listener(host, port)
                result = self._runner(
                    [sys.executable, '-m', 'carla_safety_agent.simulator_probe_worker', host, str(port)],
                    env={**os.environ, 'PYTHONPATH': os.pathsep.join(sys.path)},
                    capture_output=True, text=True, timeout=2.0, check=False,
                )
                if result.returncode != 0 or len(result.stdout) > 4096:
                    raise RuntimeError('CARLA native readiness probe failed')
                value = json.loads(result.stdout)
                if not isinstance(value, dict) or value.get('ok') is not True or not isinstance(value.get('version'), str) or not value['version'].strip():
                    raise ValueError('Invalid CARLA readiness response')
            except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
                message = f'CARLA readiness unavailable: {exc}. Offline datasets are unaffected by this probe.'
                self._cache[key] = (self._clock() + 3.0, message)
                raise RuntimeError(message) from exc
            self._cache[key] = (self._clock() + 1.0, None)


_probe = SimulatorConnectionProbe()


def require_simulator_connection(host: str, port: int) -> None:
    _probe.require(host, port)

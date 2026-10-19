from contextlib import contextmanager

import pytest

from carla_safety_agent.simulator_connection import require_simulator_listener
from carla_safety_agent.simulator_connection import SimulatorConnectionProbe
from types import SimpleNamespace
import subprocess


def test_guard_closes_probe_and_uses_short_timeout(monkeypatch):
    events = []

    @contextmanager
    def connection(address, timeout):
        events.append((address, timeout))
        yield object()
        events.append('closed')

    monkeypatch.setattr('carla_safety_agent.simulator_connection.socket.create_connection', connection)
    require_simulator_listener('127.0.0.1', 2000)
    assert events == [(('127.0.0.1', 2000), 0.25), 'closed']


@pytest.mark.parametrize('failure', [ConnectionRefusedError(), TimeoutError(), OSError('offline')])
def test_unreachable_transport_is_explicit(monkeypatch, failure):
    def connection(*args, **kwargs):
        raise failure

    monkeypatch.setattr('carla_safety_agent.simulator_connection.socket.create_connection', connection)
    with pytest.raises(RuntimeError, match='Saved datasets remain available') as caught:
        require_simulator_listener('127.0.0.1', 2000)
    assert caught.value.__cause__ is failure


def test_native_probe_uses_disposable_process_and_caches_per_endpoint(monkeypatch):
    monkeypatch.setattr('carla_safety_agent.simulator_connection.require_simulator_listener', lambda *_: None)
    calls = []
    now = [0.0]
    def runner(command, **options):
        calls.append((command, options))
        return SimpleNamespace(returncode=0, stdout='{"ok":true,"version":"0.9.15"}')
    probe = SimulatorConnectionProbe(runner=runner, clock=lambda: now[0])
    probe.require('127.0.0.1', 2000)
    probe.require('127.0.0.1', 2000)
    assert len(calls) == 1
    assert calls[0][0][-3:] == ['carla_safety_agent.simulator_probe_worker', '127.0.0.1', '2000']
    assert calls[0][1]['timeout'] == 2.0
    assert calls[0][1]['capture_output'] and not calls[0][1]['check']
    probe.require('127.0.0.1', 2001)
    assert len(calls) == 2
    now[0] = 1.01
    probe.require('127.0.0.1', 2000)
    assert len(calls) == 3


@pytest.mark.parametrize('outcome', [
    subprocess.TimeoutExpired('probe', 2), OSError('cannot spawn'),
    SimpleNamespace(returncode=-11, stdout=''),
    SimpleNamespace(returncode=0, stdout='not json'),
    SimpleNamespace(returncode=0, stdout='[]'),
    SimpleNamespace(returncode=0, stdout='{"ok":true,"version":""}'),
    SimpleNamespace(returncode=0, stdout='{"ok":false,"version":"0.9.15"}'),
    SimpleNamespace(returncode=0, stdout='x'*4097),
])
def test_unhealthy_native_probe_is_bounded_cached_and_retryable(monkeypatch, outcome):
    monkeypatch.setattr('carla_safety_agent.simulator_connection.require_simulator_listener', lambda *_: None)
    calls = []
    now = [0.0]
    def runner(*args, **kwargs):
        calls.append(1)
        if len(calls) > 1:
            return SimpleNamespace(returncode=0, stdout='{"ok":true,"version":"recovered"}')
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome
    probe = SimulatorConnectionProbe(runner=runner, clock=lambda: now[0])
    for _ in range(2):
        with pytest.raises(RuntimeError, match='readiness unavailable'):
            probe.require('127.0.0.1', 2000)
    assert len(calls) == 1
    now[0] = 3.01
    probe.require('127.0.0.1', 2000)
    assert len(calls) == 2


def test_closed_port_never_starts_native_worker(monkeypatch):
    def listener(*_):
        raise RuntimeError('offline')
    monkeypatch.setattr('carla_safety_agent.simulator_connection.require_simulator_listener', listener)
    probe = SimulatorConnectionProbe(runner=lambda *a, **kw: pytest.fail('Must not spawn'))
    with pytest.raises(RuntimeError, match='offline'):
        probe.require('127.0.0.1', 2000)

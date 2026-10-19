"""Preset-route wrapper invariants, without CARLA or model inference dependencies."""
import numpy as np
import pytest
from types import SimpleNamespace as NS

from carla_safety_agent.sensor_capture import capture_agent


class BaseAgent:
    def __init__(self):
        self.calls = 0
        self.control = object()
        self.destroyed = False

    def run_step(self, inputs, timestamp):
        self.calls += 1
        inputs['camera'][1][:] = 9
        return self.control

    def destroy(self):
        self.destroyed = True
        return 'destroyed'


class Capture:
    def __init__(self, fail=False):
        self.received = None
        self.closed = 0
        self.fail = fail

    def process(self, inputs, agent, control, **kwargs):
        self.received = (inputs, agent, control, kwargs)
        if self.fail:
            raise OSError('test capture disk failure')

    def close(self):
        self.closed += 1


def test_wrapper_preserves_single_inference_control_and_original_pixels(monkeypatch):
    monkeypatch.delenv('CSA_SENSOR_CAPTURE', raising=False)
    agent = capture_agent(BaseAgent)()
    capture = agent._capture = Capture()
    pixels = np.zeros((2, 2), dtype=np.uint8)
    assert agent.run_step({'camera': (42, pixels)}, 1.5) is agent.control
    assert agent.calls == 1
    exact, recorded_agent, control, _ = capture.received
    assert exact['camera'][0] == 42
    assert not exact['camera'][1].any()
    assert (pixels == 9).all()
    assert recorded_agent is agent and control is agent.control
    assert agent.destroy() == 'destroyed'
    assert capture.closed == 1 and agent.destroyed


def test_capture_failure_never_repeats_inference(monkeypatch, tmp_path):
    monkeypatch.delenv('CSA_SENSOR_CAPTURE', raising=False)
    monkeypatch.setenv('CSA_EVALUATION_CONTROL_DIR', str(tmp_path))
    agent = capture_agent(BaseAgent)()
    capture = agent._capture = Capture(fail=True)
    inputs = {'camera': (42, np.zeros((1, 1), dtype=np.uint8))}
    assert agent.run_step(inputs, 1.5) is agent.control
    assert agent.calls == 1 and capture.closed == 1
    assert agent._capture is None and agent._capture_failed
    assert agent.run_step(inputs, 1.6) is agent.control
    assert agent.calls == 2


def test_model_exception_is_not_retried_or_masked(monkeypatch):
    monkeypatch.delenv('CSA_SENSOR_CAPTURE', raising=False)

    class Broken(BaseAgent):
        def run_step(self, inputs, timestamp):
            self.calls += 1
            raise RuntimeError('model failed')

    agent = capture_agent(Broken)()
    with pytest.raises(RuntimeError, match='model failed'):
        agent.run_step({}, 0)
    assert agent.calls == 1


@pytest.mark.parametrize('matching', [True, False])
def test_preset_wrapper_observes_actual_pid_origin_without_recursion(monkeypatch, matching):
    monkeypatch.delenv('CSA_SENSOR_CAPTURE', raising=False)
    pid_calls = []

    class Planner(BaseAgent):
        def __init__(self):
            super().__init__()
            self.step = 0
            def pid():
                pid_calls.append(1)
                return 0, 0, False, {'wp_1': [1, 2]}
            self.net = NS(control_pid=pid)

        def run_step(self, inputs, timestamp):
            self.step += 1
            self.net.control_pid()
            return super().run_step(inputs, timestamp)

    agent = capture_agent(Planner)()
    original = agent.net.control_pid
    capture = agent._capture = Capture()
    capture.world = NS(get_snapshot=lambda: NS(frame=42, timestamp=NS(elapsed_seconds=9.5)))
    matrix = np.eye(4).tolist()
    capture.ego = NS(get_transform=lambda: NS(get_matrix=lambda: matrix))
    assert agent.run_step({'camera': (42 if matching else 41, np.zeros((1, 1)))}, 2) is agent.control
    assert agent.calls == 1 and pid_calls == [1]
    assert agent.net.control_pid is original
    planning = capture.received[3]['planning']
    if matching:
        assert planning['calls'] == 1
        assert planning['anchor'] == {'frame': 42, 'timestamp': 9.5, 'model_step': 1, 'ego_matrix': matrix}
        assert planning['outputs'] == {'wp_1': [1, 2]}
    else:
        assert planning is None

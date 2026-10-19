from types import SimpleNamespace

from carla_safety_agent.sensor_capture import SensorCapture
from carla_safety_agent.capture_quota import capture_write_lock


def test_disk_space_rechecked_after_quota_before_sample_creation(tmp_path, monkeypatch):
    capture = SensorCapture.__new__(SensorCapture)
    capture.run = tmp_path / 'capture'
    capture.run.mkdir()
    previous = capture.run / 'existing-sample'
    previous.write_bytes(b'committed data')
    capture.quota_policy = {'valid': True, 'limit_bytes': 100 * 1024**3}
    events = []
    free = 10 * 1024**3

    def quota(*args, **kwargs):
        nonlocal free
        events.append('quota')
        # Simulate another disk consumer after the initial process-level check.
        free = 1024**3 + 99
        return None

    def disk(path):
        assert path == capture.run
        events.append('disk')
        return SimpleNamespace(free=free)

    capture.manifest = lambda status: events.append(status)
    monkeypatch.setattr('carla_safety_agent.sensor_capture.check_capture_quota', quota)
    monkeypatch.setattr('carla_safety_agent.sensor_capture.shutil.disk_usage', disk)
    run = capture.run
    with capture_write_lock(tmp_path):
        capture._write_sample(2, {}, {}, {}, {}, 100)
    assert events == ['quota', 'disk', 'saved_limit']
    assert capture.run is None
    assert capture.stop_reason == 'disk_reserve'
    assert not (run / 'samples').exists()
    assert previous.read_bytes() == b'committed data'

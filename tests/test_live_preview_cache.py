import json
import os
import pytest
from carla_safety_agent.live_preview_cache import prune_previews


def cache(tmp_path):
    frames = tmp_path/'frames'
    frames.mkdir()
    for number in (1, 2, 3, 900):
        folder = frames/str(number)
        folder.mkdir()
        (folder/'CAM_FRONT.jpg').write_bytes(b'preview')
        os.utime(folder/'CAM_FRONT.jpg', (number, number))
        os.utime(folder, (number, number))
    (tmp_path/'latest.json').write_text(json.dumps({'generation':'frames/1'}))
    return frames


def test_low_current_frame_preserved_across_engine_restart(tmp_path):
    frames = cache(tmp_path)
    report = prune_previews(tmp_path, keep=2, now=2000)
    assert set(report['removed_generations']) == {'2', '3'}
    assert {p.name for p in frames.iterdir()} == {'1', '900'}


def test_unknown_contents_and_recent_readers_preserved(tmp_path):
    frames = cache(tmp_path)
    (frames/'2'/'manifest.json').write_text('{}')
    (frames/'3'/'CAM_FRONT.jpg').unlink()
    (frames/'3'/'CAM_FRONT.jpg').symlink_to('/missing')
    report = prune_previews(tmp_path, keep=1, now=910)
    assert report['removed_generations'] == []
    assert report['skipped'] == ['2', '3']


def test_bad_manifest_refuses_all_deletion(tmp_path):
    frames = cache(tmp_path)
    (tmp_path/'latest.json').write_text('{"generation":"frames/../other"}')
    with pytest.raises(ValueError):
        prune_previews(tmp_path, keep=1, now=2000)
    assert len(list(frames.iterdir())) == 4


@pytest.mark.parametrize('payload', [
    '{"generation":"frames/1","generation":"frames/900"}',
    '{"generation":"frames/1","frame":NaN}',
    '{"generation":"frames/1","nested":{"frame":1,"frame":2}}',
])
def test_ambiguous_manifest_refuses_cleanup(tmp_path, payload):
    frames=cache(tmp_path)
    latest=tmp_path/'latest.json'
    latest.write_text(payload)
    with pytest.raises(ValueError):
        prune_previews(tmp_path,keep=1,now=2000)
    assert len(list(frames.iterdir()))==4
    assert latest.read_text()==payload


@pytest.mark.parametrize('kind', ['fifo', 'oversized'])
def test_special_or_oversized_manifest_preserves_generations(tmp_path, kind):
    frames=cache(tmp_path)
    latest=tmp_path/'latest.json'
    latest.unlink()
    if kind=='fifo':
        os.mkfifo(latest)
    else:
        with latest.open('wb') as stream:
            stream.truncate(8*1024**2+1)
    with pytest.raises(ValueError,match='manifest type or size'):
        prune_previews(tmp_path,keep=1,now=2000)
    assert len(list(frames.iterdir()))==4
    assert all((folder/'CAM_FRONT.jpg').read_bytes()==b'preview' for folder in frames.iterdir())


@pytest.mark.parametrize('parameters', [
    {'grace_seconds':float('nan')}, {'grace_seconds':float('inf')},
    {'grace_seconds':True}, {'grace_seconds':'60'}, {'grace_seconds':-1},
    {'now':float('nan')}, {'now':float('inf')}, {'now':True}, {'now':-1},
    {'keep':True}, {'keep':0},
])
def test_invalid_retention_parameters_preserve_all_previews(tmp_path, parameters):
    frames=cache(tmp_path)
    before={str(p.relative_to(tmp_path)):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    with pytest.raises(ValueError, match='Invalid preview retention'):
        prune_previews(tmp_path, **parameters)
    assert len(list(frames.iterdir()))==4
    assert before=={str(p.relative_to(tmp_path)):p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}


def test_capture_holds_preview_lock_and_sweeps_old_sessions(tmp_path):
    from carla_safety_agent.sensor_capture import SensorCapture
    from carla_safety_agent.capture_quota import capture_write_lock
    frames = cache(tmp_path)
    for number in range(4, 12):
        folder = frames/str(number)
        folder.mkdir()
        (folder/'CAM_FRONT.jpg').write_bytes(b'old preview')
        os.utime(folder/'CAM_FRONT.jpg', (number, number))
        os.utime(folder, (number, number))
    capture = object.__new__(SensorCapture)
    capture.live = tmp_path
    def process(*args, **kwargs):
        with pytest.raises(OSError):
            with capture_write_lock(tmp_path):
                pytest.fail('Preview publication was not locked')
        return 'saved'
    capture._process = process
    assert capture.process({}, None, None) == 'saved'
    assert len(list(frames.iterdir())) == 6
    assert (frames/'1').exists()
    assert capture.preview_cleanup_error is None


def test_cleanup_failure_does_not_discard_successful_capture(tmp_path):
    from carla_safety_agent.sensor_capture import SensorCapture
    frames = cache(tmp_path)
    (tmp_path/'latest.json').write_text('broken')
    capture = object.__new__(SensorCapture)
    capture.live = tmp_path
    capture._process = lambda *a, **kw: 'recorded'
    assert capture.process({}, None, None) == 'recorded'
    assert capture.preview_cleanup_error
    assert len(list(frames.iterdir())) == 4


def test_fifty_restarts_respect_grace_then_converge(tmp_path):
    from carla_safety_agent.capture_quota import capture_write_lock
    frames = tmp_path/'frames'
    frames.mkdir()
    peak = 0
    for session in range(50):
        now = 1000 + session*10
        # Engine resets may produce decreasing frame numbers. Retention must
        # follow publication/mtime, not numeric frame order.
        for offset in range(3):
            number = 100000-session*10+offset
            folder = frames/str(number)
            folder.mkdir()
            (folder/'CAM_FRONT.jpg').write_bytes(b'preview')
            os.utime(folder/'CAM_FRONT.jpg', (now, now))
            os.utime(folder, (now, now))
        current = f'frames/{number}'
        (tmp_path/'latest.json').write_text(json.dumps({'generation':current}))
        with capture_write_lock(tmp_path):
            prune_previews(tmp_path, now=now)
        assert (tmp_path/current/'CAM_FRONT.jpg').read_bytes() == b'preview'
        peak = max(peak, len(list(frames.iterdir())))
        assert len(list(frames.iterdir())) <= 18
    assert peak == 18  # Six ten-second groups retained during reader grace.
    with capture_write_lock(tmp_path):
        result = prune_previews(tmp_path, now=now+61)
    assert len(list(frames.iterdir())) == 6
    assert number == int(current.split('/')[1])
    assert str(number) in result['protected']


def test_sweep_runs_periodically_not_on_every_tick(tmp_path, monkeypatch):
    from carla_safety_agent.sensor_capture import SensorCapture
    cache(tmp_path)
    capture = object.__new__(SensorCapture)
    capture.live = tmp_path
    capture._process = lambda *a, **kw: 'saved'
    calls = []
    clock = [100.0]
    monkeypatch.setattr('carla_safety_agent.sensor_capture.time.monotonic', lambda: clock[0])
    monkeypatch.setattr('carla_safety_agent.live_preview_cache.prune_previews', lambda path: calls.append(path))
    for stamp in (100, 101, 120, 159.9, 160, 161, 219.9, 220):
        clock[0] = stamp
        assert capture.process({}, None, None) == 'saved'
    assert calls == [tmp_path]*3

import json

import pytest

from carla_safety_agent.replay import replay_events


def recording(root):
    run = root / 'run'
    run.mkdir()
    (run / 'manifest.json').write_text(json.dumps({'sampling_every_frames':1}))
    frames = []
    for frame, brake in [(1,0), (2,.5), (3,.8), (5,1), (6,0), (7,.7)]:
        folder = run / str(frame)
        folder.mkdir()
        entry = {'frame':frame, 'timestamp':frame*.05, 'path':str(frame)}
        frames.append(entry)
        (folder / 'frame.json').write_text(json.dumps({**entry, 'control':{'brake':brake}}))
    (run / 'index.json').write_text(json.dumps({'frames':frames}))
    return run


def test_brake_segments_are_separated_by_release_and_recording_gap(tmp_path):
    recording(tmp_path)
    result = replay_events(tmp_path, 'run')
    assert [(e['start_frame'], e['end_frame'], e['sample_count']) for e in result['events']] == [
        (2,3,2), (5,5,1), (7,7,1)]
    assert result['events'][0]['peak_brake'] == .8
    assert result['source'] == 'recorded_control'
    assert result['collision_detection_available'] is False


@pytest.mark.parametrize('change', [{'frame':99}, {'control':{}}, {'control':{'brake':True}},
                                  {'control':{'brake':2}}])
def test_event_index_rejects_corrupt_sample(tmp_path, change):
    run = recording(tmp_path)
    path = run / '2/frame.json'
    record = json.loads(path.read_text())
    record.update(change)
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError): replay_events(tmp_path, 'run')

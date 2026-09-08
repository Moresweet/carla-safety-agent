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


def test_collision_lookup_preserves_native_frame_and_reports_nearest_sample(tmp_path):
    run = recording(tmp_path)
    event = {'kind':'collision', 'frame':4, 'timestamp':.2, 'other_actor_id':7,
             'other_actor_type':'static.prop.box01', 'normal_impulse':{'x':1,'y':2,'z':3}}
    payload = {'schema_version':'carla-collision-events/1', 'source':'sensor.other.collision',
               'events':[event], 'buffer_dropped_since_sensor_start':2,
               'invalid_observations_since_sensor_start':0}
    file = run / 'collisions.json'
    file.write_text(json.dumps(payload))
    result = replay_events(tmp_path, 'run')
    assert result['collision_detection_available']
    assert result['collisions']['buffer_dropped_since_sensor_start']==2
    found = result['collisions']['events'][0]
    assert found['frame']==4 and found['replay_frame']==3
    assert found['exact_saved_frame'] is False
    assert found['replay_time_offset_s']==pytest.approx(-.05)
    payload['events'][0]['frame']=3
    payload['events'][0]['timestamp']=.15
    file.write_text(json.dumps(payload))
    assert replay_events(tmp_path,'run')['collisions']['events'][0]['exact_saved_frame']
    payload['events'][0]['normal_impulse']['x']=True
    file.write_text(json.dumps(payload))
    with pytest.raises(ValueError,match='Invalid collision event'): replay_events(tmp_path,'run')


def test_collision_file_cannot_escape_dataset(tmp_path):
    run = recording(tmp_path)
    (tmp_path/'outside.json').write_text('{}')
    (run/'collisions.json').symlink_to(tmp_path/'outside.json')
    with pytest.raises(ValueError,match='outside dataset'): replay_events(tmp_path,'run')


def test_missing_declared_collision_file_is_not_reported_as_legacy(tmp_path):
    run = recording(tmp_path)
    (run/'manifest.json').write_text(json.dumps({'files':{'collisions':'collisions.json'}}))
    with pytest.raises(ValueError,match='recording is missing'): replay_events(tmp_path,'run')

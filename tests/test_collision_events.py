from types import SimpleNamespace

from carla_safety_agent.collision_events import CollisionEvents


def event(frame):
    return SimpleNamespace(frame=frame, timestamp=frame*.05,
        normal_impulse=SimpleNamespace(x=1,y=2,z=3),
        other_actor=SimpleNamespace(id=7,type_id='static.prop.box01'))


def test_native_observations_are_bounded_and_recording_filtered():
    log = CollisionEvents(capacity=2)
    for frame in (1,2,3): log.receive(event(frame))
    result = log.snapshot(3)
    assert result['source'] == 'sensor.other.collision'
    assert result['buffer_dropped_since_sensor_start'] == 1
    assert len(result['events']) == 1
    assert result['events'][0]['frame'] == 3
    assert result['events'][0]['normal_impulse'] == {'x':1.,'y':2.,'z':3.}


def test_nonfinite_observation_is_not_serialized():
    log = CollisionEvents()
    invalid = event(1)
    invalid.normal_impulse.x = float('nan')
    log.receive(invalid)
    assert log.snapshot(0)['events'] == []

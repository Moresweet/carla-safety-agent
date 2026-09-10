import pytest

from carla_safety_agent.sensor_schedule import synchronous_specs
from leaderboard.envs.sensor_interface import SensorInterface, SensorReceivedNoData


def test_requested_interval_preserved_but_native_sampling_is_every_step():
    original = [{'id': 'IMU', 'type': 'sensor.other.imu', 'sensor_tick': .05},
                {'id': 'GPS', 'type': 'sensor.other.gnss', 'sensor_tick': .01},
                {'id': 'CAM', 'type': 'sensor.camera.rgb'},
                {'id': 'SPEED', 'type': 'sensor.speedometer'}]
    actual = synchronous_specs(original, .05)
    assert original[0]['sensor_tick'] == .05
    assert [spec['sensor_tick'] for spec in actual[:3]] == [0, 0, 0]
    assert [spec['requested_sensor_tick'] for spec in actual[:3]] == [.05, .01, 0]
    assert all(spec['effective_period_seconds'] == .05 for spec in actual[:3])
    assert actual[3] == original[3]


@pytest.mark.parametrize('interval', [.1, -1, True, float('nan'), float('inf'), '.05'])
def test_unsupported_sparse_or_invalid_sensor_rate_rejected(interval):
    with pytest.raises(ValueError):
        synchronous_specs([{'id': 'IMU', 'type': 'sensor.other.imu', 'sensor_tick': interval}], .05)


def test_missing_frame_diagnostic_never_substitutes_stale_input():
    interface = SensorInterface()
    interface.register_sensor('IMU', 'sensor.other.imu', None)
    interface.update_sensor('IMU', [1, 2, 3], 42)
    with pytest.raises(SensorReceivedNoData, match="last received frames: {'IMU': 42}"):
        interface.get_data(43, timeout=0)
    assert interface.get_data(42, timeout=0)['IMU'][0] == 42

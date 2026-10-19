from carla_safety_agent.opendrive_sensor_profile import original_sensor_specs
import pytest


@pytest.mark.parametrize('size', [192, 512])
def test_model_specific_debug_camera_resolution_is_preserved(size):
    spec = {'id': 'topdown', 'type': 'sensor.camera.rgb', 'width': size,
            'height': size, 'x': 0., 'y': 0., 'z': 50., 'pitch': -90., 'fov': 50.}
    configured = original_sensor_specs([spec])[0]
    assert all(configured[key] == value for key, value in spec.items())
    assert configured['blueprint_attributes']['lens_circle_multiplier'] == '3.0'


def test_original_lidar_contract_is_explicit_and_does_not_mutate_input():
    specs = [{'type': 'sensor.lidar.ray_cast', 'id': 'lidar', 'z': 2.5}]
    result = original_sensor_specs(specs)
    assert 'blueprint_attributes' not in specs[0]
    assert result[0]['z'] == 2.5
    assert result[0]['blueprint_attributes'] == {
        'range': '85', 'rotation_frequency': '10', 'channels': '64',
        'upper_fov': '10', 'lower_fov': '-30', 'points_per_second': '600000',
        'atmosphere_attenuation_rate': '0.004', 'dropoff_general_rate': '0.45',
        'dropoff_intensity_limit': '0.8', 'dropoff_zero_intensity': '0.4'}


def test_camera_and_navigation_noise_contracts():
    kinds = ['sensor.camera.rgb', 'sensor.camera.depth', 'sensor.other.imu',
             'sensor.other.gnss', 'sensor.speedometer']
    rgb, depth, imu, gnss, speed = original_sensor_specs([{'type': k} for k in kinds])
    assert rgb['blueprint_attributes']['chromatic_aberration_intensity'] == '0.5'
    assert depth['blueprint_attributes'] == {
        'lens_circle_multiplier': '3.0', 'lens_circle_falloff': '3.0'}
    assert imu['blueprint_attributes']['noise_accel_stddev_z'] == '0.015'
    assert len(imu['blueprint_attributes']) == 6
    assert set(gnss['blueprint_attributes'].values()) == {'0.0'}
    assert 'blueprint_attributes' not in speed

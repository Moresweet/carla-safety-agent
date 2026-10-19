"""Explicit original OpenDriveLab leaderboard blueprint attributes.

Source: ThinkTwice e9cf2fc, leaderboard/autoagents/agent_wrapper.py.
DriveAdapter 4275652 uses a byte-identical agent_wrapper.py (audited locally).
Opt-in through the model wrapper; never change other agents' defaults.
"""
from copy import deepcopy


def original_sensor_specs(specs):
    result = deepcopy(specs)
    for spec in result:
        kind = spec['type']
        attributes = {}
        if kind.startswith('sensor.camera'):
            attributes = dict(lens_circle_multiplier=3.0, lens_circle_falloff=3.0)
            if kind == 'sensor.camera.rgb':
                attributes.update(chromatic_aberration_intensity=0.5,
                                  chromatic_aberration_offset=0)
        elif kind == 'sensor.lidar.ray_cast':
            attributes = dict(range=85, rotation_frequency=10, channels=64,
                              upper_fov=10, lower_fov=-30, points_per_second=600000,
                              atmosphere_attenuation_rate=0.004, dropoff_general_rate=0.45,
                              dropoff_intensity_limit=0.8, dropoff_zero_intensity=0.4)
        elif kind == 'sensor.other.gnss':
            attributes = dict(noise_alt_bias=0.0, noise_lat_bias=0.0, noise_lon_bias=0.0)
        elif kind == 'sensor.other.imu':
            attributes = dict(noise_accel_stddev_x=0.001, noise_accel_stddev_y=0.001,
                              noise_accel_stddev_z=0.015, noise_gyro_stddev_x=0.001,
                              noise_gyro_stddev_y=0.001, noise_gyro_stddev_z=0.001)
        if attributes:
            spec['blueprint_attributes'] = {key: str(value) for key, value in attributes.items()}
    return result

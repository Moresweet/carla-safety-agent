"""Explicit every-frame schedule for the native executor's synchronous rig."""
import math


def synchronous_specs(specs, fixed_delta_seconds):
    if (isinstance(fixed_delta_seconds, bool) or
            not isinstance(fixed_delta_seconds, (int, float)) or
            not math.isfinite(fixed_delta_seconds) or fixed_delta_seconds <= 0):
        raise ValueError('Invalid synchronous step')
    result = []
    for original in specs:
        spec = dict(original)
        if spec['type'] != 'sensor.speedometer':
            interval = spec.get('sensor_tick', 0)
            if (isinstance(interval, bool) or not isinstance(interval, (int, float)) or
                    not math.isfinite(interval) or interval < 0 or interval > fixed_delta_seconds):
                raise ValueError(f"Sensor {spec['id']} cannot supply every synchronous frame")
            spec.update(requested_sensor_tick=interval, sensor_tick=0.0,
                        sampling_policy='every_synchronous_frame',
                        effective_period_seconds=fixed_delta_seconds)
        result.append(spec)
    return result

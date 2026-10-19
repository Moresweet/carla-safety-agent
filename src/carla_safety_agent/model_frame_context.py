"""Opt-in exact simulator identity delivery before model preprocessing."""
import math

from .opendrive_history import FrameIdentity


def deliver_frame_context(agent, world, frame, sensor_data):
    hook = getattr(agent, 'set_simulator_frame', None)
    if hook is None:
        return
    if not callable(hook):
        raise ValueError('Model frame hook is not callable')
    snapshot = world.get_snapshot()
    timestamp = snapshot.timestamp.elapsed_seconds
    if (type(frame) is not int or frame < 0 or snapshot.frame != frame or
            type(world.id) is not int or world.id < 0 or
            isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)) or
            not math.isfinite(timestamp) or timestamp < 0):
        raise ValueError('Simulator snapshot does not identify the model input frame')
    if not sensor_data:
        raise ValueError('Model input frame has no sensors')
    for sensor_id, sample in sensor_data.items():
        if (not isinstance(sample, (tuple, list)) or len(sample) != 2 or
                type(sample[0]) is not int or sample[0] != frame):
            raise ValueError(f'Sensor {sensor_id} does not match the model input frame')
    hook(FrameIdentity(world.id, frame, timestamp))

"""Bounded native collision observations; no inference from vehicle controls."""
import math
import threading
from collections import deque


class CollisionEvents:
    def __init__(self, capacity=10000):
        self.capacity = capacity
        self.events = deque()
        self.dropped = 0
        self.invalid = 0
        self.lock = threading.Lock()

    def receive(self, event):
        impulse = {axis: float(getattr(event.normal_impulse, axis)) for axis in ('x','y','z')}
        timestamp = float(event.timestamp)
        if not math.isfinite(timestamp) or not all(math.isfinite(v) for v in impulse.values()):
            with self.lock:
                self.invalid += 1
            return
        record = {'kind':'collision', 'frame':int(event.frame), 'timestamp':timestamp,
                  'other_actor_id':int(event.other_actor.id),
                  'other_actor_type':str(event.other_actor.type_id), 'normal_impulse':impulse}
        with self.lock:
            if len(self.events) >= self.capacity:
                self.events.popleft()
                self.dropped += 1
            self.events.append(record)

    def snapshot(self, start_frame):
        with self.lock:
            return {'schema_version':'carla-collision-events/1', 'source':'sensor.other.collision',
                    'events':[dict(event) for event in self.events if event['frame'] >= start_frame],
                    'buffer_dropped_since_sensor_start':self.dropped,
                    'invalid_observations_since_sensor_start':self.invalid,
                    'note':'Asynchronous sensor observations received before finalization; late callbacks may be absent.'}

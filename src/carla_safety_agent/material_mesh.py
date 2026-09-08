"""Validate exported triangle-list XYZ/UV previews without inventing geometry."""
import json
import math


def validate_preview(payload):
    if len(payload) > 32*1024*1024:
        raise ValueError('Preview mesh exceeds 32 MiB')
    value = json.loads(payload)
    if not isinstance(value, dict): raise ValueError('Preview mesh must be an object')
    count, vertices = value.get('triangleCount'), value.get('vertices')
    if isinstance(count, bool) or not isinstance(count, int) or not 0 < count <= 1000000:
        raise ValueError('Invalid preview triangle count')
    if not isinstance(vertices, list) or len(vertices) != count*15:
        raise ValueError('Preview requires three XYZ/UV vertices per triangle')
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in vertices):
        raise ValueError('Preview vertices must be finite numbers')
    return value

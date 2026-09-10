"""Pinhole depth cross-check, explicitly not a definitive visibility label."""
import numpy as np

from .projection import project_points


def compare_depth(points, source, depth_camera, depth, rgb_indices):
    depth = np.asarray(depth)
    if (depth.dtype.kind != 'f' or depth.ndim != 2 or
            depth.shape != (depth_camera.get('height'), depth_camera.get('width')) or
            depth.size > 16000000):
        raise ValueError('Invalid or oversized depth image')
    projected = project_points(points, source, depth_camera)
    # Reproject using the depth sensor's own intrinsics/extrinsics. Do not assume
    # that auxiliary depth and model RGB have identical resolution or poses.
    uv = np.floor(projected['pixels']).astype(int)
    measured = depth[uv[:, 1], uv[:, 0]]
    valid = np.isfinite(measured) & (measured > 0) & (measured < 999.99)
    residual = projected['depth'] - measured
    tolerance = np.maximum(.5, .02 * measured)
    states = np.full(len(points), 'unknown', dtype='<U10')
    ids = projected['indices'][valid]
    states[ids] = 'consistent'
    states[ids[residual[valid] > tolerance[valid]]] = 'behind'
    states[ids[residual[valid] < -tolerance[valid]]] = 'in_front'
    selected = states[np.asarray(rgb_indices, dtype=int)]
    counts = {name: int(np.count_nonzero(selected == name))
              for name in ('consistent', 'behind', 'in_front', 'unknown')}
    return {'states': selected, 'counts': counts,
            'tolerance_absolute_m': .5, 'tolerance_relative': .02,
            'sampling': 'floor_pixel_in_independent_depth_projection',
            'depth_convention': 'optical_forward_z_m',
            'occlusion_ground_truth': False}

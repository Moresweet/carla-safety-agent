"""Project recorded CARLA sensor points using explicit saved calibration.

No inference of missing legacy extrinsics, no simulator connection or mutation.
Returned indices refer to the original point array; depth is optical forward Z.
"""
import numpy as np


def project_box(vertices, world_to_ego, camera):
    """Native CARLA vertex order; clip edges to near plane and image bounds.

    Geometry only: does not test depth occlusion or object visibility.
    """
    points = np.asarray(vertices, dtype=float)
    if points.shape != (8, 3) or not np.isfinite(points).all():
        raise ValueError('Expected eight finite world vertices')
    # Reuse the rigid calibration validation, treating world as the source.
    source = {'sensor_to_ego': world_to_ego}
    project_points(np.empty((0, 3)), source, camera)
    transform = (np.asarray(camera['sensor_to_optical']) @
                 np.asarray(camera['ego_to_sensor']) @ np.asarray(world_to_ego))
    optical = (transform @ np.column_stack((points, np.ones(8))).T).T[:, :3]
    intrinsic = np.asarray(camera['K'])
    width, height = camera['width'], camera['height']
    segments = []
    # BoundingBox.h orders signs as xyz binary bits: one changed bit = edge.
    for i in range(8):
        for bit in (1, 2, 4):
            j = i ^ bit
            if j < i:
                continue
            a, b = optical[i].copy(), optical[j].copy()
            near = .01
            if max(a[2], b[2]) < near:
                continue
            if a[2] < near:
                a += (b-a)*((near-a[2])/(b[2]-a[2]))
            if b[2] < near:
                b += (a-b)*((near-b[2])/(a[2]-b[2]))
            uv = (intrinsic @ np.stack((a, b)).T).T
            a, b = uv[:, :2]/uv[:, 2, None]
            delta = b-a
            lo, hi = 0., 1.
            for axis, maximum in ((0, width-1), (1, height-1)):
                if abs(delta[axis]) < 1e-12:
                    if not 0 <= a[axis] <= maximum:
                        hi = -1.
                else:
                    t0, t1 = sorted((-a[axis]/delta[axis], (maximum-a[axis])/delta[axis]))
                    lo, hi = max(lo, t0), min(hi, t1)
            if lo <= hi:
                segments.append([*(a+lo*delta).tolist(), *(a+hi*delta).tolist()])
    return segments


def project_points(points, source, camera):
    points = np.asarray(points)
    if points.ndim != 2 or points.shape[1] not in (3,4) or points.dtype.kind not in 'fiu':
        raise ValueError('Expected N x 3 or N x 4 points')
    matrices = []
    for spec, key, shape in ((source,'sensor_to_ego',(4,4)),
                             (camera,'ego_to_sensor',(4,4)),
                             (camera,'sensor_to_optical',(4,4)),
                             (camera,'K',(3,3))):
        if key not in spec:
            raise ValueError(f'Missing calibration: {key}')
        matrix = np.asarray(spec[key],dtype=float)
        if matrix.shape != shape or not np.isfinite(matrix).all():
            raise ValueError(f'Invalid calibration: {key}')
        if shape == (4,4):
            rotation=matrix[:3,:3]
            if (not np.allclose(matrix[3],[0,0,0,1]) or
                not np.allclose(rotation.T @ rotation,np.eye(3),atol=1e-6) or
                not np.isclose(np.linalg.det(rotation),-1 if key=='sensor_to_optical' else 1,atol=1e-6)):
                raise ValueError(f'Non-rigid calibration: {key}')
        elif matrix[0,0]<=0 or matrix[1,1]<=0 or not np.allclose(matrix[2],[0,0,1]):
            raise ValueError('Invalid camera intrinsic matrix')
        matrices.append(matrix)
    width,height = camera.get('width'),camera.get('height')
    if any(isinstance(v,bool) or not isinstance(v,int) or v <= 0 for v in (width,height)):
        raise ValueError('Invalid camera dimensions')
    indices=np.flatnonzero(np.isfinite(points[:,:3]).all(axis=1))
    homogeneous=np.column_stack((points[indices,:3],np.ones(len(indices))))
    pose,inverse,optical,intrinsic=matrices
    transformed=(optical @ inverse @ pose @ homogeneous.T).T[:,:3]
    front=transformed[:,2] > 1e-6
    transformed,indices=transformed[front],indices[front]
    projected=(intrinsic @ transformed.T).T
    pixels=projected[:,:2]/projected[:,2,None]
    inside=(pixels[:,0]>=0)&(pixels[:,0]<width)&(pixels[:,1]>=0)&(pixels[:,1]<height)
    return {'indices':indices[inside], 'pixels':pixels[inside], 'depth':transformed[inside,2]}

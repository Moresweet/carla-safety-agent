"""Project recorded CARLA sensor points using explicit saved calibration.

No inference of missing legacy extrinsics, no simulator connection or mutation.
Returned indices refer to the original point array; depth is optical forward Z.
"""
import numpy as np


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

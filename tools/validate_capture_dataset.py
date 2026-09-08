"""Validate committed multimodal samples, not just the existence of files."""
import json
import sys
from pathlib import Path
import numpy as np
from PIL import Image

root = Path(sys.argv[1]).resolve()
manifest = json.loads((root/'manifest.json').read_text())
archive = manifest.get('input_archive', 'model_input.npz')
assert archive in ('model_input.npz', 'sensor_input.npz'), 'Unknown input archive'
index = json.loads((root/'index.json').read_text())['frames']
calibration = json.loads((root/'calibration.json').read_text())
extrinsics_checked = 0
for name, spec in calibration.items():
    if 'sensor_to_ego' not in spec and 'ego_to_sensor' not in spec:
        continue  # Legacy data remains readable; do not claim it has verified extrinsics.
    forward = np.asarray(spec['sensor_to_ego'],dtype=float)
    inverse = np.asarray(spec['ego_to_sensor'],dtype=float)
    assert forward.shape == inverse.shape == (4,4), 'Invalid extrinsic shape'
    assert np.isfinite(forward).all() and np.isfinite(inverse).all(), 'Non-finite extrinsics'
    assert np.allclose(forward[3],[0,0,0,1]), 'Invalid homogeneous transform'
    assert np.allclose(forward @ inverse,np.eye(4),atol=1e-6), 'Extrinsics are not inverse'
    rotation=forward[:3,:3]
    assert np.allclose(rotation.T @ rotation,np.eye(3),atol=1e-6), 'Non-rigid extrinsics'
    assert np.isclose(np.linalg.det(rotation),1,atol=1e-6), 'Invalid rotation determinant'
    extrinsics_checked += 1
assert index, 'No recorded samples'
previous = -1
for entry in index:
    folder = root/'samples'/f"{entry['frame']:010d}"
    meta = json.loads((folder/'frame.json').read_text())
    assert meta['synchronized'] and not meta['missing']
    assert meta['frame'] == entry['frame'], 'Index/sample frame mismatch'
    assert meta['frame'] > previous
    previous = meta['frame']
    with np.load(folder/archive, allow_pickle=False) as model:
        if archive == 'sensor_input.npz':
            assert meta['model'] is None and meta['actual_model_inputs']==[]
            required = ('CAM_FRONT','CAM_FRONT_LEFT','CAM_FRONT_RIGHT','CAM_BACK','CAM_BACK_LEFT','CAM_BACK_RIGHT')
        else:
            required = meta['actual_model_inputs']
            assert required, 'No actual model inputs recorded'
        assert set(required).issubset(model.files), 'Missing raw input arrays'
        for name in ('CAM_FRONT','CAM_FRONT_LEFT','CAM_FRONT_RIGHT','CAM_BACK','CAM_BACK_LEFT','CAM_BACK_RIGHT'):
            rgb = np.asarray(Image.open(folder/(name+'.png')))
            assert rgb.ndim == 3 and rgb.shape[2] == 3, 'Invalid RGB shape'
            if name in model:
                assert model[name].dtype == np.uint8 and model[name].shape == (*rgb.shape[:2],4), 'Invalid raw BGRA'
                assert np.array_equal(rgb, model[name][:,:,:3][:,:,::-1]), name
            depth = np.load(folder/('DEPTH_'+name+'.npy'), allow_pickle=False)
            # Early captures used NumPy 1.x promotion to float64; retain them.
            assert depth.dtype in (np.dtype('float32'), np.dtype('float64')) and depth.ndim == 2
            # Auxiliary depth can intentionally use lower resolution than model RGB.
            for sensor, shape in ((name,rgb.shape[:2]),('DEPTH_'+name,depth.shape)):
                spec = calibration[sensor]
                if 'height' in spec and 'width' in spec:
                    assert shape == (spec['height'],spec['width']), 'Calibration/image dimensions disagree'
            assert np.isfinite(depth).all() and 0 <= depth.min() <= depth.max() <= 1000.01
    lidar = np.load(folder/'LIDAR.npy', allow_pickle=False)
    assert lidar.ndim == 2 and lidar.shape[1] == 4 and np.isfinite(lidar).all()
    for name in ('BEV_POINTS', 'BEV_RGB'):
        Image.open(folder/(name+'.png')).verify()
print(f'PASS: {len(index)} synchronized samples, {archive} RGB verified, metric depth, XYZI, BEV: {root.name}')
print(f'Extrinsics verified: {extrinsics_checked}/{len(calibration)} sensors (legacy missing extrinsics are not verified)')

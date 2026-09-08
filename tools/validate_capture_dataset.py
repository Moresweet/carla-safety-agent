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
            assert depth.shape == rgb.shape[:2], 'RGB/depth dimensions disagree'
            assert np.isfinite(depth).all() and 0 <= depth.min() <= depth.max() <= 1000.01
    lidar = np.load(folder/'LIDAR.npy', allow_pickle=False)
    assert lidar.ndim == 2 and lidar.shape[1] == 4 and np.isfinite(lidar).all()
    for name in ('BEV_POINTS', 'BEV_RGB'):
        Image.open(folder/(name+'.png')).verify()
print(f'PASS: {len(index)} synchronized samples, {archive} RGB verified, metric depth, XYZI, BEV: {root.name}')

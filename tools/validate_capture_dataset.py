"""Validate committed multimodal samples, not just the existence of files."""
import json
import sys
from pathlib import Path
import numpy as np
from PIL import Image

root = Path(sys.argv[1]).resolve()
index = json.loads((root/'index.json').read_text())['frames']
assert index, 'No recorded samples'
previous = -1
for entry in index:
    folder = root/'samples'/f"{entry['frame']:010d}"
    meta = json.loads((folder/'frame.json').read_text())
    assert meta['synchronized'] and not meta['missing']
    assert meta['frame'] > previous
    previous = meta['frame']
    with np.load(folder/'model_input.npz', allow_pickle=False) as model:
        for name in ('CAM_FRONT','CAM_FRONT_LEFT','CAM_FRONT_RIGHT','CAM_BACK','CAM_BACK_LEFT','CAM_BACK_RIGHT'):
            rgb = np.asarray(Image.open(folder/(name+'.png')))
            if name in model:
                assert np.array_equal(rgb, model[name][:,:,:3][:,:,::-1]), name
            depth = np.load(folder/('DEPTH_'+name+'.npy'), allow_pickle=False)
            # Early captures used NumPy 1.x promotion to float64; retain them.
            assert depth.dtype in (np.dtype('float32'), np.dtype('float64')) and depth.ndim == 2
            assert np.isfinite(depth).all() and 0 <= depth.min() <= depth.max() <= 1000.01
    lidar = np.load(folder/'LIDAR.npy', allow_pickle=False)
    assert lidar.ndim == 2 and lidar.shape[1] == 4 and np.isfinite(lidar).all()
    for name in ('BEV_POINTS', 'BEV_RGB'):
        Image.open(folder/(name+'.png')).verify()
print(f'PASS: {len(index)} synchronized samples, exact model RGB, metric depth, XYZI, BEV: {root.name}')

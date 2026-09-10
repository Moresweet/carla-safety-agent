"""Small isolated sensor fixtures: prove corrupted captures cannot report PASS."""
import json
from pathlib import Path
import sys
import tempfile
import uuid

import numpy as np
from PIL import Image

from carla_safety_agent.capture_quality import audit_capture

ROOT = Path(__file__).resolve().parents[1]
CAMERAS = ('CAM_FRONT', 'CAM_FRONT_LEFT', 'CAM_FRONT_RIGHT',
           'CAM_BACK', 'CAM_BACK_LEFT', 'CAM_BACK_RIGHT')


def fixture(root):
    folder = root/'samples/0000000001'
    folder.mkdir(parents=True)
    (root/'manifest.json').write_text(json.dumps({'frame_count':1, 'input_archive':'sensor_input.npz'}))
    (root/'index.json').write_text(json.dumps({'frames':[{'frame':1,'timestamp':1.,'path':'samples/0000000001'}]}))
    (folder/'frame.json').write_text(json.dumps({'frame':1,'timestamp':1.,'model':None,
        'actual_model_inputs':[],'synchronized':True,'missing':[], 'sensor_frames':{},
        'auxiliary_frames':{name:1 for name in (*CAMERAS,*('DEPTH_'+name for name in CAMERAS),'LIDAR','BEV_RGB')}}))
    calibration = {}
    raw = {}
    for name in CAMERAS:
        Image.fromarray(np.zeros((2,2,3), dtype=np.uint8)).save(folder/(name+'.png'))
        np.save(folder/('DEPTH_'+name+'.npy'), np.ones((2,2), dtype=np.float32))
        raw[name] = np.zeros((2,2,4), dtype=np.uint8)
        for sensor in (name,'DEPTH_'+name):
            calibration[sensor] = {'width':2,'height':2,'sensor_to_ego':np.eye(4).tolist(),
                                    'ego_to_sensor':np.eye(4).tolist()}
    (root/'calibration.json').write_text(json.dumps(calibration))
    np.savez(folder/'sensor_input.npz', **raw)
    np.save(folder/'LIDAR.npy', np.zeros((2,4), dtype=np.float32))
    for name in ('BEV_POINTS','BEV_RGB'):
        Image.fromarray(np.zeros((2,2,3), dtype=np.uint8)).save(folder/(name+'.png'))
    return folder


def main():
    cases = {}
    for kind in ('valid','timestamp','sensor_frame','depth_nan','missing_input','rgb_mismatch','count','extrinsics'):
        with tempfile.TemporaryDirectory(prefix='carla-quality-fixture-') as temporary:
            root = Path(temporary)
            folder = fixture(root)
            if kind == 'timestamp':
                meta=json.loads((folder/'frame.json').read_text());meta['timestamp']=2.
                (folder/'frame.json').write_text(json.dumps(meta))
            elif kind == 'sensor_frame':
                meta=json.loads((folder/'frame.json').read_text());meta['auxiliary_frames']['LIDAR']=2
                (folder/'frame.json').write_text(json.dumps(meta))
            elif kind == 'depth_nan':
                np.save(folder/'DEPTH_CAM_FRONT.npy', np.full((2,2), np.nan, dtype=np.float32))
            elif kind == 'missing_input':
                np.savez(folder/'sensor_input.npz', CAM_FRONT=np.zeros((2,2,4), dtype=np.uint8))
            elif kind == 'rgb_mismatch':
                Image.fromarray(np.full((2,2,3), 255, dtype=np.uint8)).save(folder/'CAM_FRONT.png')
            elif kind == 'count':
                (root/'manifest.json').write_text(json.dumps({'frame_count':2,'input_archive':'sensor_input.npz'}))
            elif kind == 'extrinsics':
                calibration=json.loads((root/'calibration.json').read_text())
                calibration['CAM_FRONT']['sensor_to_ego'][0][0]=2
                (root/'calibration.json').write_text(json.dumps(calibration))
            report = audit_capture(root, ROOT/'tools/validate_capture_dataset.py', sys.executable)
            expected = 'passed' if kind == 'valid' else 'failed'
            if report['state'] != expected:
                raise RuntimeError(f'{kind}: expected {expected}, got {report}')
            cases[kind] = report
    output = ROOT/'runs/validation'/('capture-quality-'+uuid.uuid4().hex+'.json')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({'cases':cases,'scope':'Synthetic corruption rejection; no simulator or existing dataset writes'},indent=2))
    print(output)


if __name__ == '__main__':
    main()

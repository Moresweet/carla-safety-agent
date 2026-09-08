import json
import numpy as np
import pytest
from carla_safety_agent.replay import replay_boxes
from carla_safety_agent.sensor_capture import calibration


@pytest.mark.parametrize('defect', [None, 'null_actor', 'null_vertices', 'duplicate', 'bad_calibration', 'bad_pose'])
def test_legacy_boxes_and_malformed_data(tmp_path, defect):
    run = tmp_path/'run'; folder = run/'1'; folder.mkdir(parents=True)
    (run/'manifest.json').write_text('{}')
    (run/'index.json').write_text(json.dumps({'frames': [{'frame': 1, 'path': '1'}]}))
    camera = calibration(dict(type='sensor.camera.rgb', width=640, height=360,
                              fov=90, x=0, y=0, z=0))
    if defect == 'bad_calibration': camera['width'] = 0
    (run/'calibration.json').write_text(json.dumps({'CAM_FRONT': camera}))
    actor = {'id': 2, 'type': 'static.prop.test'}
    actors = [actor]
    if defect == 'null_actor': actors = [None]
    if defect == 'duplicate': actors = [actor, actor]
    if defect == 'null_vertices': actor['bounding_box'] = {'world_vertices': None}
    pose = np.eye(4)
    if defect == 'bad_pose': pose[0, 0] = 2
    (folder/'frame.json').write_text(json.dumps({'frame': 1, 'actors': actors,
                                                'ego': {'id': 1, 'matrix': pose.tolist()}}))
    if defect:
        with pytest.raises(ValueError): replay_boxes(tmp_path, 'run', 1, 'CAM_FRONT')
    else:
        result = replay_boxes(tmp_path, 'run', 1, 'CAM_FRONT')
        assert result['boxes'] == [] and result['missing_geometry'] == 1

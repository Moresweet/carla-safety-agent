import numpy as np
import pytest

from carla_safety_agent.depth_consistency import compare_depth
from carla_safety_agent.sensor_capture import calibration


def camera(**kwargs):
    return calibration(dict(type='sensor.camera.depth',width=4,height=4,fov=90,x=0,y=0,z=0,**kwargs))


def test_depth_labels_preserve_original_point_ids():
    points = [[10,0,0],[12,0,0],[8,0,0],[-1,0,0]]
    report = compare_depth(points,camera(),camera(),np.full((4,4),10.),[2,0,3,1])
    assert report['states'].tolist() == ['in_front','consistent','unknown','behind']
    assert sum(report['counts'].values()) == 4
    assert not report['occlusion_ground_truth']


def test_depth_camera_own_pose_and_invalid_pixels():
    depth = camera(yaw=90)
    report = compare_depth([[0,10,0]],camera(),depth,np.full((4,4),10.),[0])
    assert report['states'].tolist() == ['consistent']
    for invalid in (0.,1000.,float('nan'),float('inf')):
        report = compare_depth([[10,0,0]],camera(),camera(),np.full((4,4),invalid),[0])
        assert report['states'].tolist() == ['unknown']


def test_depth_dimensions_must_match_saved_calibration():
    with pytest.raises(ValueError):
        compare_depth([[10,0,0]],camera(),camera(),np.ones((8,8)),[0])


def test_replay_requires_same_frame_depth_and_timestamp(tmp_path):
    import json
    from carla_safety_agent.replay import replay_projection
    root = tmp_path/'capture-a'
    folder = root/'samples/0000000001'
    folder.mkdir(parents=True)
    (root/'manifest.json').write_text('{}')
    (root/'index.json').write_text(json.dumps({'frames':[{'frame':1,'timestamp':1.,'path':'samples/0000000001'}]}))
    (root/'calibration.json').write_text(json.dumps({'LIDAR':camera(),'CAM_FRONT':camera(),'DEPTH_CAM_FRONT':camera()}))
    np.save(folder/'LIDAR.npy', np.array([[10,0,0,.5]]))
    np.save(folder/'DEPTH_CAM_FRONT.npy', np.full((4,4),10.))
    metadata = {'frame':1,'timestamp':1.,'synchronized':True,'missing':[],
                'sensor_frames':{'CAM_FRONT':1},'auxiliary_frames':{'DEPTH_CAM_FRONT':1,'LIDAR':1}}
    (folder/'frame.json').write_text(json.dumps(metadata))
    result = replay_projection(tmp_path,'capture-a',1,'CAM_FRONT',True)
    assert result['depth_consistency']['states'] == ['consistent']
    for changes in ({'timestamp':2.}, {'auxiliary_frames':{'DEPTH_CAM_FRONT':2,'LIDAR':1}},
                    {'synchronized':False}, {'sensor_frames':{'CAM_FRONT':2}}):
        (folder/'frame.json').write_text(json.dumps({**metadata,**changes}))
        with pytest.raises(ValueError):
            replay_projection(tmp_path,'capture-a',1,'CAM_FRONT',True)

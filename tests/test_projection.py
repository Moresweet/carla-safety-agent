import numpy as np
import pytest
from carla_safety_agent.projection import project_points
from carla_safety_agent.sensor_capture import calibration


def camera(**pose):
    return calibration(dict(type='sensor.camera.rgb',width=640,height=360,fov=90,
                            x=0,y=0,z=0,**pose))


def test_projection_axes_filtering_and_original_indices():
    c=camera()
    points=[[10,0,0],[10,1,1],[-10,0,0],[0,0,0],[1,100,0],[np.nan,0,0]]
    result=project_points(points,c,c)
    assert result['indices'].tolist()==[0,1]
    assert result['pixels']==pytest.approx(np.array([[320,180],[352,148]]))
    assert result['depth']==pytest.approx([10,10])


def test_projection_respects_source_translation_and_camera_rotation():
    source=calibration(dict(type='sensor.lidar.ray_cast',x=0,y=10,z=0))
    result=project_points([[0,0,0]],source,camera(yaw=90))
    assert result['pixels']==pytest.approx(np.array([[320,180]]))
    assert result['depth']==pytest.approx([10])


def test_projection_rejects_missing_extrinsics_and_accepts_empty_cloud():
    with pytest.raises(ValueError,match='Missing calibration'):
        project_points([[1,2,3]],{},camera())
    assert project_points(np.empty((0,4)),camera(),camera())['pixels'].shape==(0,2)


def test_replay_projection_is_bounded_and_frame_confined(tmp_path):
    import json
    from carla_safety_agent.replay import replay_projection
    root=tmp_path/'run'; folder=root/'samples'/'1'; folder.mkdir(parents=True)
    (root/'manifest.json').write_text('{}')
    (root/'index.json').write_text(json.dumps({'frames':[{'frame':1,'path':'samples/1'}]}))
    (root/'calibration.json').write_text(json.dumps({'LIDAR':camera(),'CAM_FRONT':camera()}))
    np.save(folder/'LIDAR.npy',np.tile([10,0,0,.5],(10001,1)))
    result=replay_projection(tmp_path,'run',1,'CAM_FRONT')
    assert result['visible_count']==10001 and len(result['pixels'])<=5000
    assert result['occlusion_checked'] is False
    with pytest.raises(ValueError): replay_projection(tmp_path,'run',2,'CAM_FRONT')
    with pytest.raises(ValueError): replay_projection(tmp_path,'run',1,'../camera')

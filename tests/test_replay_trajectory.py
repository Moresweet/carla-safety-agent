import json
import numpy as np
import pytest
from carla_safety_agent.replay import replay_trajectory


def test_recorded_trajectory_is_relative_and_separates_future(tmp_path):
    root=tmp_path/'run'; root.mkdir()
    (root/'manifest.json').write_text('{}')
    entries=[]
    for frame in range(3):
        folder=root/str(frame);folder.mkdir()
        pose=np.eye(4);pose[0,3]=frame*2
        (folder/'frame.json').write_text(json.dumps({'frame':frame,'timestamp':float(frame),'ego':{'matrix':pose.tolist()}}))
        entries.append({'frame':frame,'timestamp':float(frame),'path':str(frame)})
    (root/'index.json').write_text(json.dumps({'frames':entries}))
    result=replay_trajectory(tmp_path,'run',1)
    assert [p['xyz_m'] for p in result['history']]==[[-2,0,0],[0,0,0]]
    assert result['future'][0]['xyz_m']==[2,0,0]
    assert result['source']=='recorded_ego_pose' and result['interpolated'] is False
    assert replay_trajectory(tmp_path,'run',2)['future']==[]
    for horizon in (True,0,float('nan'),31):
        with pytest.raises(ValueError): replay_trajectory(tmp_path,'run',1,horizon)

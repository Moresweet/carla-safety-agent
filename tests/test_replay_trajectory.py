import json
import numpy as np
import pytest
from carla_safety_agent.replay import replay_trajectory


@pytest.mark.parametrize('bad_frame', [0, 1, 2])
@pytest.mark.parametrize('defect', ['scale', 'shear', 'reflection', 'projective', 'nan'])
def test_trajectory_rejects_nonrigid_current_history_and_future(tmp_path, bad_frame, defect):
    root = tmp_path / 'run'
    root.mkdir()
    (root / 'manifest.json').write_text('{}')
    entries = []
    for frame in range(3):
        folder = root / str(frame)
        folder.mkdir()
        pose = np.eye(4)
        pose[0, 3] = frame
        if frame == bad_frame:
            if defect == 'scale': pose[0, 0] = 2
            elif defect == 'shear': pose[0, 1] = .2
            elif defect == 'reflection': pose[0, 0] = -1
            elif defect == 'projective': pose[3, 0] = .2
            else: pose[0, 0] = float('nan')
        (folder / 'frame.json').write_text(json.dumps({'frame': frame,
            'timestamp': float(frame), 'ego': {'matrix': pose.tolist()}}))
        entries.append({'frame': frame, 'timestamp': float(frame), 'path': str(frame)})
    (root / 'index.json').write_text(json.dumps({'frames': entries}))
    before = {p: p.read_bytes() for p in root.rglob('*.json')}
    with pytest.raises(ValueError, match='rigid ego poses'):
        replay_trajectory(tmp_path, 'run', 1)
    assert all(p.read_bytes() == value for p, value in before.items())


def test_recorded_trajectory_is_relative_and_separates_future(tmp_path,monkeypatch):
    root=tmp_path/'run'; root.mkdir()
    (root/'manifest.json').write_text('{}')
    entries=[]
    for frame in range(3):
        folder=root/str(frame);folder.mkdir()
        pose=np.eye(4);pose[0,3]=frame*2
        (folder/'frame.json').write_text(json.dumps({'frame':frame,'timestamp':float(frame),'ego':{'matrix':pose.tolist()}}))
        entries.append({'frame':frame,'timestamp':float(frame),'path':str(frame)})
    (root/'index.json').write_text(json.dumps({'frames':entries}))
    from pathlib import Path
    original_read=Path.read_text
    reads=[]
    def tracked_read(path,*args,**kwargs):
        if path.name=='index.json': reads.append(path)
        return original_read(path,*args,**kwargs)
    monkeypatch.setattr(Path,'read_text',tracked_read)
    result=replay_trajectory(tmp_path,'run',1)
    assert len(reads)==1, 'Trajectory must not reread its full index for every sample'
    assert [p['xyz_m'] for p in result['history']]==[[-2,0,0],[0,0,0]]
    assert result['future'][0]['xyz_m']==[2,0,0]
    assert result['source']=='recorded_ego_pose' and result['interpolated'] is False
    assert replay_trajectory(tmp_path,'run',2)['future']==[]
    for horizon in (True,0,float('nan'),31):
        with pytest.raises(ValueError): replay_trajectory(tmp_path,'run',1,horizon)
    record=json.loads((root/'2/frame.json').read_text());record['timestamp']=2.1
    (root/'2/frame.json').write_text(json.dumps(record))
    with pytest.raises(ValueError,match='identity mismatch'):
        replay_trajectory(tmp_path,'run',1)


def test_future_reference_follows_rotating_lidar_lever_arm(tmp_path):
    from carla_safety_agent.prediction_trajectory import spatial_contract,PID
    root=tmp_path/'run';root.mkdir();(root/'manifest.json').write_text('{}')
    entries=[]
    for frame in range(2):
        pose=np.eye(4)
        if frame:pose[:2,:2]=[[0,-1],[1,0]];pose[0,3]=10
        folder=root/str(frame);folder.mkdir()
        raw=[[0.,10.],[0.,20.]]
        anchor={'frame':frame,'model_step':frame,'timestamp':float(frame),'ego_matrix':pose.tolist()}
        metadata={'frame':frame,'model_step':frame,'timestamp':float(frame),'source':'model-input','model':'vad',
                  'ego':{'matrix':pose.tolist()},'outputs':{'plan':raw},'planning_outputs':{'plan':raw},'planning_anchor':anchor,
                  'prediction':{'state':'available','contract':spatial_contract('vad',PID),
                                'right_forward_m':raw,'anchor':anchor,'timing_verified':False}}
        (folder/'frame.json').write_text(json.dumps(metadata))
        entries.append({'frame':frame,'timestamp':float(frame),'path':str(frame)})
    (root/'index.json').write_text(json.dumps({'frames':entries}))
    result=replay_trajectory(tmp_path,'run',0)
    assert result['prediction']['state']=='available'
    assert result['prediction']['reference_history'][0]['xyz_m']==[-.39,0.,1.84]
    assert result['prediction']['reference_future'][0]['xyz_m']==[10.,-.39,1.84]
    assert result['future'][0]['xyz_m']==[10.,0.,0.]

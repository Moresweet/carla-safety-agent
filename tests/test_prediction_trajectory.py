from types import SimpleNamespace as NS
import numpy as np
import pytest
from carla_safety_agent import prediction_trajectory as prediction


def sample(model='vad',pose=None):
    points=[[2.,10.],[3.,20.],[4.,30.],[5.,40.]]
    outputs={'plan':points,**{'wp_'+str(i+1):p for i,p in enumerate(points)}}
    if model=='admlp':
        outputs={key:[*value,.2] for key,value in outputs.items() if key!='plan'}
    anchor={'frame':10,'model_step':1,'timestamp':1.,'ego_matrix':(np.eye(4) if pose is None else pose).tolist()}
    return {'source':'model-input','model':model,'outputs':outputs,'planning_outputs':outputs,
            'frame':10,'model_step':1,'timestamp':1.,'planning_anchor':anchor,
            'prediction':{'state':'available','contract':prediction.spatial_contract(model,prediction.CONTROLLERS[model]),
                          'right_forward_m':[p[::-1] for p in points] if model in ('thinktwice','driveadapter') else points,'anchor':anchor,'timing_verified':False}}


@pytest.mark.parametrize('model',list(prediction.CONTROLLERS))
def test_capture_contract_only_with_matching_controller_source(monkeypatch,model):
    agent=NS(net=NS(control_pid=lambda:None),pidcontroller=NS(control_pid=lambda:None),model=NS(control_pid=lambda:None),
             lidar2ego=[[0,1,0,-.39],[-1,0,0,0],[0,0,1,1.84],[0,0,0,1]])
    metadata=sample(model)
    monkeypatch.setattr(prediction,'controller_digest',lambda _:prediction.CONTROLLERS[model])
    assert prediction.capture_prediction(agent,metadata)==metadata['prediction']
    monkeypatch.setattr(prediction,'controller_digest',lambda _:'changed')
    assert prediction.capture_prediction(agent,metadata)['state']=='unavailable'


@pytest.mark.parametrize('model',['driveadapter','driveadapter-experimental','thinktwice','vad'])
def test_replay_discloses_navigation_reference_without_rewriting_saved_contract(model):
    import copy
    metadata=sample(prediction.ALIASES.get(model,model))
    metadata['model']=model
    original=copy.deepcopy(metadata)
    result=prediction.replay_prediction(metadata,np.eye(4))
    assert result['state']=='available'
    assert bool(result['reference_warning'])==model.startswith('driveadapter')
    assert result['timing_verified'] is False
    assert result['error_metrics_computed'] is False
    assert metadata==original


def test_forward_right_mapping_and_yaw_invariance():
    pose=np.eye(4);pose[:2,:2]=[[0,-1],[1,0]];pose[:3,3]=[100,200,30]
    result=prediction.replay_prediction(sample('admlp',pose),pose)
    assert result['points'][0]['xyz_m']==[10.,2.,0.]
    assert result['points'][0]['dt_s'] is None


@pytest.mark.parametrize('model', ['thinktwice', 'driveadapter'])
def test_original_saved_pid_points_are_forward_right_not_virtual_lidar(model):
    metadata=sample(model)
    result=prediction.replay_prediction(metadata,np.eye(4))
    assert result['state']=='available'
    assert result['points'][0]['xyz_m']==[2.,10.,0.]
    assert result['contract']['raw_axes']=='forward_right'
    assert result['contract']['reference_offset_body_m']==[0.,0.,0.]
    assert result['timing_verified'] is False
    assert result['timing_verified'] is False and result['error_metrics_computed'] is False


@pytest.mark.parametrize('name',['UniadAgent','UniADAgent','UniAD-Tiny','UniAD-Base'])
def test_reviewed_uniad_runtime_names_keep_source_gate(monkeypatch,name):
    model=prediction.ALIASES[name]
    metadata=sample(model);metadata['model']=name
    agent=NS(pidcontroller=NS(control_pid=lambda:None),
             lidar2ego=[[0,1,0,-.39],[-1,0,0,0],[0,0,1,1.84],[0,0,0,1]])
    monkeypatch.setattr(prediction,'controller_digest',lambda _:prediction.PID)
    metadata['prediction']=prediction.capture_prediction(agent,metadata)
    assert prediction.replay_prediction(metadata,np.eye(4))['state']=='available'
    monkeypatch.setattr(prediction,'controller_digest',lambda _:'changed')
    assert prediction.capture_prediction(agent,metadata)['state']=='unavailable'


def test_prediction_heading_plane_transforms_to_pitched_body():
    angle=.3;pose=np.eye(4)
    pose[:3,:3]=[[np.cos(angle),0,-np.sin(angle)],[0,1,0],[np.sin(angle),0,np.cos(angle)]]
    result=prediction.replay_prediction(sample('admlp',pose),pose)
    assert result['state']=='available'
    np.testing.assert_allclose(result['points'][0]['xyz_m'],[10*np.cos(angle),2,-10*np.sin(angle)])


@pytest.mark.parametrize('damage',['missing','source','model','digest','timing','coordinates','raw','nonfinite','bool'])
def test_unverified_or_inconsistent_prediction_is_not_overlaid(damage):
    metadata=sample()
    if damage=='missing':metadata.pop('prediction')
    if damage=='source':metadata['source']='sensor-rig'
    if damage=='model':metadata['model']='unknown'
    if damage=='digest':metadata['prediction']['contract']['controller_sha256']='changed'
    if damage=='timing':metadata['prediction']['contract']['point_dt_s']=.5
    if damage=='coordinates':metadata['prediction']['contract']['raw_axes']='forward_right'
    if damage=='raw':metadata['prediction']['right_forward_m']=[[99,99]]
    if damage=='nonfinite':metadata['outputs']['plan'][0][0]=float('nan')
    if damage=='bool':metadata['outputs']['plan'][0][0]=True
    result=prediction.replay_prediction(metadata,np.eye(4))
    assert result['state']=='unavailable' and result['points']==[]


def test_missing_controller_does_not_break_capture():
    assert prediction.capture_prediction(NS(),sample())['state']=='unavailable'
    assert prediction.capture_prediction(NS(),{'source':'sensor-rig'})['state']=='unavailable'


def test_non_rigid_pose_is_not_used_for_prediction():
    pose=np.eye(4);pose[0,0]=2
    assert prediction.replay_prediction(sample(),pose)['state']=='unavailable'


def test_lidar_prediction_is_not_mislabeled_as_ego_center():
    result=prediction.replay_prediction(sample(),np.eye(4))
    assert result['contract']['reference']=='virtual_lidar'
    assert result['points'][0]['xyz_m']==[9.61,2.,1.84]


def test_early_contract_with_unverified_origin_is_refused():
    metadata=sample();metadata['prediction']['contract']['schema_version']='carla-prediction-spatial/1'
    assert prediction.replay_prediction(metadata,np.eye(4))['state']=='unavailable'


@pytest.mark.parametrize('failure',[False,True])
@pytest.mark.parametrize('owner_name',['net','model'])
def test_tcp_observes_planning_branch_without_replacing_control(failure,owner_name):
    from carla_safety_agent.planning_observation import PlanningObservation
    calls=[];chosen=object()
    class Base:
        def run_step(self,inputs,timestamp):
            getattr(self,owner_name).control_pid('original_prediction')
            self.pid_metadata={'agent':'only_ctrl'}
            if failure:raise RuntimeError('inference failure')
            return chosen
    agent=Base();agent.step=1
    def original(value):calls.append(value);return 0,0,False,{'wp_1':(2,10)}
    setattr(agent,owner_name,NS(control_pid=original))
    observer=PlanningObservation(agent)
    def run():return observer.run_step({},0,frame=10,timestamp=1.,ego_matrix=np.eye(4).tolist())
    if failure:
        with pytest.raises(RuntimeError,match='inference failure'):run()
    else:
        assert run() is chosen
    assert getattr(agent,owner_name).control_pid is original and calls==['original_prediction']
    assert observer.snapshot()['outputs']=={'wp_1':(2,10)} and agent.pid_metadata=={'agent':'only_ctrl'}


def test_reused_prediction_is_transformed_from_original_pose():
    metadata=sample('admlp');metadata.update(frame=12,model_step=3,timestamp=1.1)
    current=np.eye(4);current[0,3]=2
    result=prediction.replay_prediction(metadata,current)
    assert result['points'][0]['xyz_m']==[8.,2.,0.]
    assert result['reused'] and result['prediction_age_s']==pytest.approx(.1)
    assert result['source_frame']==10


def test_observation_retains_original_anchor_when_model_reuses_control():
    from carla_safety_agent.planning_observation import PlanningObservation
    class Agent:
        step=-1
        def run_step(self,inputs,elapsed):
            self.step+=1
            self._planning_navigation_reference={'model_step':self.step,'world_xy_m':[self.step,0.]}
            if self.step==0:
                self.net.control_pid()
                self._planning_navigation_reference['world_xy_m'][0]=999
            return 'unchanged control'
    agent=Agent();agent.net=NS(control_pid=lambda:(0,0,False,{'wp_1':(1,2)}))
    observer=PlanningObservation(agent)
    for frame in (10,11):
        assert observer.run_step({},0,frame=frame,timestamp=float(frame),ego_matrix=np.eye(4).tolist())=='unchanged control'
    assert observer.snapshot()['calls']==1 and observer.snapshot()['anchor']['frame']==10
    assert observer.snapshot()['anchor']['navigation_reference']['world_xy_m']==[0,0.]


def test_warmup_is_explicit_not_a_fabricated_prediction(monkeypatch):
    agent=NS(net=NS(control_pid=lambda:None))
    monkeypatch.setattr(prediction,'controller_digest',lambda _:prediction.CONTROLLERS['tcp'])
    metadata=sample('tcp');metadata.update(model_step=0,planning_anchor=None,planning_warmup_steps=1,planning_observed_calls=0)
    assert prediction.capture_prediction(agent,metadata)['state']=='warmup'
    metadata['model_step']=1
    assert prediction.capture_prediction(agent,metadata)['state']=='unavailable'


def test_admlp_heading_component_is_preserved_raw_but_not_treated_as_height():
    metadata=sample('admlp')
    result=prediction.replay_prediction(metadata,np.eye(4))
    assert result['points'][0]['xyz_m']==[10.,2.,0.]
    assert metadata['planning_outputs']['wp_1']==[2.,10.,.2]
    assert result['contract']['ignored_for_spatial_plot']==['relative_heading_rad']

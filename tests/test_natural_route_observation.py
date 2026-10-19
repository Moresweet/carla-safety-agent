import importlib.util
from pathlib import Path
import sys


def load(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]/'tools'))
    spec=importlib.util.spec_from_file_location('natural_route_observation_test',Path(__file__).resolve().parents[1]/'tools/regression_natural_route.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_observation_preserves_controls_and_labels_wall_time(monkeypatch):
    module=load(monkeypatch)
    source={'frame':25,'inputs':{'speed_mps':1.4},'outputs':{'controller':{'throttle':0.5,'brake':0,'desired_speed_mps':7.4}}}
    result=module.motion_observation(source,100)
    assert result=={'frame':25,'observed_wall_elapsed_s':100,'speed_mps':1.4,'throttle':0.5,'brake':0,'desired_speed_mps':7.4,'steer':None}
    assert 'steer' not in source['outputs']['controller']


def test_missing_or_invalid_controls_are_not_zero(monkeypatch):
    module=load(monkeypatch)
    result=module.motion_observation({'frame':1,'inputs':{'speed_mps':float('nan')},'outputs':{'controller':{'brake':True,'throttle':'0.5'}}},2)
    assert all(result[key] is None for key in ('speed_mps','brake','throttle','desired_speed_mps','steer'))


def completed_report():
    return {'route':'26406','cleanup_confirmed':True,'natural_terminal':True,
            'execution_healthy':True,'final_results':{'_checkpoint':{'records':[
                {'route_id':'RouteScenario_26406_rep0','status':'Completed','scores':{'score_route':100}}
            ]}}}


def test_acceptance_requires_completed_matching_route(monkeypatch):
    module=load(monkeypatch)
    report=completed_report()
    assert module.acceptance_outcome(report)['exit_code']==0
    record=report['final_results']['_checkpoint']['records'][0]
    record['status']='Perfect'
    assert module.acceptance_outcome(report)['exit_code']==0
    record['status']='Completed'
    record['scores']['score_route']=3.83
    assert module.acceptance_outcome(report)['passed'] is False
    record['scores']['score_route']=100
    record['status']='Failed'
    assert module.acceptance_outcome(report)['passed'] is False
    record['status']='Completed'
    record['route_id']='RouteScenario_other_rep0'
    assert module.acceptance_outcome(report)['reason']=='route_result_unverified'


def test_timeout_cleanup_and_missing_results_never_pass(monkeypatch):
    module=load(monkeypatch)
    report=completed_report()
    report['natural_terminal']=False
    assert module.acceptance_outcome(report)['exit_code']==2
    report['cleanup_confirmed']=False
    assert module.acceptance_outcome(report)['exit_code']==1
    for invalid in (None, {}, {'_checkpoint':None}, {'_checkpoint':{'records':[]}}):
        report=completed_report();report['final_results']=invalid
        assert module.acceptance_outcome(report)['passed'] is False


def test_invalid_completion_is_not_evidence(monkeypatch):
    module=load(monkeypatch)
    for value in (True, '100', float('nan'), float('inf'), None):
        report=completed_report()
        report['final_results']['_checkpoint']['records'][0]['scores']['score_route']=value
        assert module.acceptance_outcome(report)['reason']=='route_result_unverified'

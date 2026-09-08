"""Local HTTP compiler contract; never starts or modifies the CARLA world."""
import json
import urllib.error
from regression_scene_versions import ROOT, request


def main():
    root=ROOT/'.runtime/generated-scenarios'
    before=set(root.glob('plan-*.json'))
    invalid=[{'description':None},{'description':' '},{'seed':True},{'seed':1.5},
             {'seed':'7'},{'seed':-1},{'seed':2**32},{'max_duration_s':False},
             {'max_duration_s':-1},{'max_duration_s':0},{'max_duration_s':'2'},
             {'max_duration_s':float('nan')},{'max_duration_s':float('inf')}]
    for options in invalid:
        try:
            request('scenario/compile',{'description':'Town04 前车急刹',**options})
        except urllib.error.HTTPError as exc:
            assert exc.code==400, exc.code
            error=json.load(exc)
            assert error['ok'] is False and error['error']
        else:
            raise AssertionError(f'Invalid options accepted: {options}')
    assert set(root.glob('plan-*.json'))==before, 'Invalid request created a plan'
    valid=request('scenario/compile',{'description':'Town04 大雨前车急刹，自车 5 m/s',
                                      'seed':7,'max_duration_s':2})
    assert valid['plan_review']['oracle']['max_duration_s']==2
    assert valid['plan_review']['environment']['precipitation']==70
    assert valid['build_plan']['trigger']['actors'][0]['action']=='hard_brake'
    assert valid['scenario_sha256']==valid['plan_review']['scenario_sha256']
    distances=[]
    for distance in (18,25,12.5):
        compiled=request('scenario/compile',{'description':f'Town04 前车在{distance}米处急刹，自车速度5 m/s'})
        assert compiled['scenario']['adversaries'][0]['trigger_distance_m']==distance
        assert compiled['build_plan']['trigger']['threshold_m']==distance
        assert not any(w.startswith('trigger_not_specified') for w in compiled['warnings'])
        distances.append(distance)
    print(json.dumps({'invalid_rejected':len(invalid),'invalid_created_files':0,
                      'valid_plan':valid['scenario_sha256'],'actors':len(valid['build_plan']['actors']),
                      'explicit_braking_distances':distances}))


if __name__=='__main__': main()

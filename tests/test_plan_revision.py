import copy
from pathlib import Path
import pytest
from carla_safety_agent.natural_language import NaturalLanguageCompiler
from carla_safety_agent.plan_revision import revise_plan
from carla_safety_agent.scenario_archive import archive_scenario,read_verified_scenario
from test_studio_bridge import functions


def base():return NaturalLanguageCompiler().compile('Town04 大雨夜间，前车在18米处急刹，自车速度15 m/s',7).scenario.to_dict()


def test_only_requested_fields_change_and_parent_not_mutated():
    parent=base();before=copy.deepcopy(parent)
    child,changes=revise_plan(parent,'a'*64,'自车速度改为36 km/h；雨量改为20%；其余保持不变')
    assert parent==before
    assert child['ego']['speed_mps']==10 and child['environment']['precipitation']==20
    assert child['adversaries']==parent['adversaries'] and child['generated_assets']==parent['generated_assets']
    assert child['environment']['sun_altitude_angle']==-10
    for key in ('map_name','seed','oracle','generated_map'):assert child[key]==parent[key]
    assert {c['path'] for c in changes}=={'ego/speed_mps','environment/precipitation'}
    lineage=child['provenance']['plan_revision'];assert lineage['parent_sha256']=='a'*64 and lineage['depth']==1


@pytest.mark.parametrize('instruction',[
    '自车速度改为-2 m/s','自车速度改为90 m/s','自车速度改为5','雨量改为101%',
    '运行时长改为0秒','运行时长改为121秒','随机种子改为1.2','触发距离改为0米',
    '自车速度改为5 m/s；添加一辆飞车','自车速度改为5 m/s；自车速度改为6 m/s',
    '天气改为大雨；雨量改为30','改成更危险','地图改为Town05并删除全部车辆',
    '雨量改为20 m','光照改为任意','其余不变'])
def test_unsupported_ambiguous_or_out_of_range_edits_are_atomic(instruction):
    parent=base();before=copy.deepcopy(parent)
    with pytest.raises(ValueError):revise_plan(parent,'a'*64,instruction)
    assert parent==before


def test_fields_weather_map_seed_trigger_and_duration():
    child,_=revise_plan(base(),'a'*64,'地图改为Town05_Opt；随机种子改为4294967295；触发距离改为25米；运行时长改为1秒；天气改为晴天；光照改为白天')
    assert child['map_name']=='Town05_Opt' and child['seed']==2**32-1
    assert child['adversaries'][0]['trigger_distance_m']==25 and child['oracle']['max_duration_s']==1
    assert child['environment']['precipitation']==child['environment']['fog_density']==0
    assert child['environment']['sun_altitude_angle']==45


def test_asset_edit_keeps_dimensions_and_rejects_generated_map_replacement():
    parent=NaturalLanguageCompiler().compile('生成一条S弯新道路，前方35米掉落6根金属管').scenario.to_dict()
    child,_=revise_plan(parent,'b'*64,'金属管数量改为8根')
    assert child['generated_assets'][0]['count']==8
    assert child['generated_assets'][0]['dimensions_m']==parent['generated_assets'][0]['dimensions_m']
    assert child['generated_map']==parent['generated_map']
    for instruction in ('地图改为Town05','触发距离改为10米','对手速度改为3 m/s'):
        with pytest.raises(ValueError):revise_plan(parent,'b'*64,instruction)


def test_revision_depth_is_bounded():
    parent=base();parent['provenance']['plan_revision']={'depth':32}
    with pytest.raises(ValueError):revise_plan(parent,'a'*64,'雨量改为20')


def test_bridge_archives_new_plan_without_simulator_access(tmp_path):
    root=tmp_path/'.runtime/generated-scenarios';path,digest=archive_scenario(root,base());old=path.read_bytes()
    env=functions('revise_scenario',PROJECT_ROOT=tmp_path,Path=Path,archive_scenario=archive_scenario,
        read_verified_scenario=read_verified_scenario,build_plan=__import__('carla_safety_agent.build_plan',fromlist=['build_plan']).build_plan)
    result=env['revise_scenario']({'scenario_path':str(path),'scenario_sha256':digest,'instruction':'自车速度改为5 m/s'})
    assert result['scenario_sha256']!=digest and path.read_bytes()==old
    child,_=read_verified_scenario(result['scenario_path'],result['scenario_sha256'])
    assert child['ego']['speed_mps']==5 and result['parent_sha256']==digest
    for bad in [dict(scenario_path='/tmp/outside.json',scenario_sha256=digest,instruction='雨量改为20'),
                dict(scenario_path=str(path),scenario_sha256=digest,instruction='雨量改为20',execute=True)]:
        with pytest.raises(ValueError):env['revise_scenario'](bad)

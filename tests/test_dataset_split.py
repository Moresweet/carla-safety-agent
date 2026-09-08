import pytest
from carla_safety_agent.dataset_split import split_runs


def test_related_runs_never_cross_splits_and_order_does_not_matter():
    runs=[{'run_id':str(i),'scene_group':str(i//3)} for i in range(90)]
    result=split_runs(runs)
    assert result==split_runs(list(reversed(runs)))
    locations={run:split for split,ids in result['assignments'].items() for run in ids}
    assert len(locations)==90
    for i in range(0,90,3): assert len({locations[str(j)] for j in range(i,i+3)})==1
    expanded=split_runs(runs+[{'run_id':'new','scene_group':'new-scene'}])
    assert all(expanded['scene_groups'][g]==v for g,v in result['scene_groups'].items())


@pytest.mark.parametrize('runs',[[{'run_id':'a'}],[{'run_id':'a','scene_group':''}],
    [{'run_id':'a','scene_group':'x'},{'run_id':'a','scene_group':'y'}]])
def test_split_rejects_unknown_scene_or_duplicate_run(runs):
    with pytest.raises(ValueError): split_runs(runs)


def test_invalid_ratios_and_explicit_single_split():
    with pytest.raises(ValueError): split_runs([],ratios=(1,1,0))
    result=split_runs([{'run_id':'a','scene_group':'x'}],ratios=(0,0,1))
    assert result['assignments']['test']==['a']


def test_cli_creates_manifest_without_overwriting(tmp_path):
    import json
    import os
    import subprocess
    import sys
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    source=tmp_path/'groups.json';target=tmp_path/'split.json'
    source.write_text(json.dumps([{'run_id':'recorded-run','scene_group':'scene-version-1'}]))
    command=[sys.executable,str(root/'tools/split_capture_datasets.py'),str(source),str(target)]
    env={**os.environ,'PYTHONPATH':str(root/'src')}
    subprocess.run(command,env=env,check=True,capture_output=True)
    before=target.read_bytes()
    assert json.loads(before)['run_count']==1
    assert subprocess.run(command,env=env,capture_output=True).returncode!=0
    assert target.read_bytes()==before

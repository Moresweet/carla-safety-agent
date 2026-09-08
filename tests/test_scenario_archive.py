import pytest
from carla_safety_agent.scenario_archive import archive_scenario
from carla_safety_agent.scenario_archive import read_verified_scenario


def test_content_identity_preserves_different_options(tmp_path):
    first = {'scenario_id':'same','oracle':{'max_duration_s':10}}
    path, digest = archive_scenario(tmp_path,first)
    assert archive_scenario(tmp_path,dict(reversed(list(first.items())))) == (path,digest)
    other, changed = archive_scenario(tmp_path,{**first,'oracle':{'max_duration_s':20}})
    assert path != other and digest != changed and path.is_file() and other.is_file()
    path.write_text('corrupt')
    with pytest.raises(ValueError,match='differs'): archive_scenario(tmp_path,first)
    assert path.read_text()=='corrupt'


def test_archive_rejects_nonfinite_and_symlink(tmp_path):
    with pytest.raises(ValueError): archive_scenario(tmp_path,{'speed':float('nan')})
    payload={'scenario_id':'test'}
    path,_=archive_scenario(tmp_path,payload)
    target=tmp_path/'target'
    path.rename(target)
    path.symlink_to(target)
    with pytest.raises(ValueError): archive_scenario(tmp_path,payload)


def test_execution_reads_verified_bytes_and_rejects_changed_plan(tmp_path):
    document={'scenario_id':'test'}
    path,digest=archive_scenario(tmp_path,document)
    assert read_verified_scenario(path,digest)==(document,digest)
    with pytest.raises(ValueError,match='changed'): read_verified_scenario(path,'0'*64)
    path.write_text('{"scenario_id":"changed"}')
    with pytest.raises(ValueError,match='identity'): read_verified_scenario(path)


def test_legacy_file_can_be_pinned_without_claiming_content_addressing(tmp_path):
    path=tmp_path/'legacy.json'
    path.write_text('{"scenario_id":"legacy"}')
    document,digest=read_verified_scenario(path)
    assert read_verified_scenario(path,digest)==(document,digest)
    path.write_text('{"scenario_id":"another"}')
    with pytest.raises(ValueError,match='changed'): read_verified_scenario(path,digest)


def test_native_executor_verifies_before_accessing_carla():
    import ast
    from pathlib import Path
    source=Path(__file__).resolve().parents[1]/'src/carla_safety_agent/native_executor.py'
    tree=ast.parse(source.read_text())
    executor=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='NativeScenarioExecutor')
    run=next(n for n in executor.body if isinstance(n,ast.FunctionDef) and n.name=='run')
    calls={n.func.id:n.lineno for n in ast.walk(run) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)}
    assert calls['read_verified_scenario']<calls['scenario_from_dict']<calls['CarlaAdapter']

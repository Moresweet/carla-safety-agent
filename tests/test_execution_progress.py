import json
from pathlib import Path
import pytest
from carla_safety_agent.execution_progress import ExecutionProgress,read_progress,progress_from_environment


def fixture(tmp_path):
    root=tmp_path/'data';(root/'experiments/run').mkdir(parents=True)
    owner={'pid':123,'start_ticks':'456'}
    progress=ExecutionProgress(root,'run',owner,clock=lambda:100)
    session={'run_id':'run','state':'running','process':owner}
    return root,progress,session


def test_bound_progress_countdown_and_terminal_last_report(tmp_path):
    root,progress,session=fixture(tmp_path)
    progress.emit('preview',completed_steps=20,total_steps=20,preview_seconds=60)
    before=progress.path.read_bytes()
    result=read_progress(root,session,now=120)
    assert result['available'] and result['preview_remaining_s']==40 and result['age_s']==20
    assert read_progress(root,session,now=170)['preview_remaining_s']==0
    terminal=read_progress(root,{**session,'state':'completed'},now=120)
    assert not terminal['active'] and terminal['preview_remaining_s'] is None
    assert progress.path.read_bytes()==before


@pytest.mark.parametrize('change',[{'run_id':'other'},{'owner':{'pid':123,'start_ticks':'789'}},
    {'phase':'made_up'},{'completed_steps':True},{'completed_steps':21},{'updated_at':float('nan')},
    {'preview_until':999999},{'extra':'unexpected'}])
def test_untrusted_report_is_not_presented_as_current_progress(tmp_path,change):
    root,progress,session=fixture(tmp_path)
    progress.emit('preview',completed_steps=20,total_steps=20,preview_seconds=60)
    row=json.loads(progress.path.read_text());row.update(change);progress.path.write_text(json.dumps(row))
    result=read_progress(root,session,now=120)
    assert not result['available'] and result['invalid']


def test_missing_old_future_and_symlink_reports_fail_closed(tmp_path):
    root,progress,session=fixture(tmp_path)
    assert not read_progress(root,session)['available']
    progress.emit('loading_model')
    assert not read_progress(root,session,now=80)['available']
    assert not read_progress(root,{**session,'run_id':'other'},now=100)['available']
    raw=progress.path.read_bytes();progress.path.unlink();target=tmp_path/'other.json';target.write_bytes(raw)
    progress.path.symlink_to(target)
    assert read_progress(root,session,now=100)['invalid']


def test_advisory_write_failure_disables_reporting_not_simulation(tmp_path,monkeypatch,capsys):
    _,progress,_=fixture(tmp_path)
    calls=[]
    def fail(*_):calls.append(1);raise OSError('disk failure')
    monkeypatch.setattr('carla_safety_agent.execution_progress.atomic',fail)
    progress.emit('connecting');progress.emit('inference',completed_steps=0,total_steps=20)
    assert progress.disabled and calls==[1]
    assert 'simulation continues' in capsys.readouterr().out


def test_factory_does_not_invent_legacy_worker_identity(monkeypatch):
    monkeypatch.delenv('CSA_RESOURCE_DATA_ROOT',raising=False)
    monkeypatch.delenv('CSA_EXECUTION_ID',raising=False)
    assert progress_from_environment() is None

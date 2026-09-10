from pathlib import Path
import pytest
from carla_safety_agent.session import observed_process_identity


@pytest.mark.parametrize('error', [PermissionError, OSError, ValueError])
def test_observation_errors_are_not_absence(monkeypatch, error):
    def read(_): raise error('unavailable')
    monkeypatch.setattr(Path, 'read_text', read)
    with pytest.raises(error): observed_process_identity(123)


def test_missing_pid_and_zombie_are_absent(monkeypatch):
    def missing(_): raise FileNotFoundError()
    monkeypatch.setattr(Path, 'read_text', missing)
    assert observed_process_identity(123) is None
    text = '123 (worker (name)) ' + ' '.join(['Z'] + ['0']*18 + ['789'])
    monkeypatch.setattr(Path, 'read_text', lambda _: text)
    assert observed_process_identity(123) is None
    monkeypatch.setattr(Path, 'read_text', lambda _: text.replace(' Z ', ' S '))
    assert observed_process_identity(123) == {'pid': 123, 'start_ticks': '789'}


def test_malformed_stat_is_not_absence(monkeypatch):
    monkeypatch.setattr(Path, 'read_text', lambda _: 'truncated')
    with pytest.raises(ValueError): observed_process_identity(123)


@pytest.mark.parametrize('error',[PermissionError,OSError,ValueError])
def test_session_reconciliation_cannot_assume_owner_absent(tmp_path,monkeypatch,error):
    import os
    from carla_safety_agent.session import SessionJournal
    journal=SessionJournal(tmp_path);journal.begin('test',{});journal.attach(os.getpid())
    before=journal.snapshot();saved=(tmp_path/'session.json').read_bytes()
    def unavailable(_):raise error('identity observation unavailable')
    monkeypatch.setattr('carla_safety_agent.session.observed_process_identity',unavailable)
    with pytest.raises(error):journal.owned_pid()
    with pytest.raises(error):journal.reconcile()
    assert journal.snapshot()==before and (tmp_path/'session.json').read_bytes()==saved


def test_attach_observation_failure_does_not_claim_running_without_identity(tmp_path,monkeypatch):
    from carla_safety_agent.session import SessionJournal
    journal=SessionJournal(tmp_path);journal.begin('test',{})
    before=journal.snapshot()
    def unavailable(_):raise PermissionError('identity unavailable')
    monkeypatch.setattr('carla_safety_agent.session.observed_process_identity',unavailable)
    with pytest.raises(PermissionError):journal.attach(123)
    assert journal.snapshot()==before


@pytest.mark.parametrize('identity',[{},False,{'pid':True,'start_ticks':'1'},
    {'pid':1,'start_ticks':'invalid'},{'pid':0,'start_ticks':'1'},{'pid':1,'start_ticks':'1','other':1}])
def test_malformed_persisted_owner_blocks_recovery(tmp_path,identity):
    from carla_safety_agent.session import SessionJournal
    journal=SessionJournal(tmp_path);journal.begin('test',{})
    journal.state['process']=identity
    with pytest.raises(ValueError,match='process identity'):journal.owned_pid()
    with pytest.raises(ValueError,match='process identity'):journal.reconcile()
    assert journal.snapshot()['state']=='preparing'

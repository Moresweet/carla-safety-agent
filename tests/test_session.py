import os
import pytest
from carla_safety_agent.session import SessionJournal, process_identity


def test_identity_does_not_match_recycled_pid(tmp_path):
    journal = SessionJournal(tmp_path)
    journal.begin('test', {'seed': 7})
    journal.attach(os.getpid())
    assert journal.owned_pid() == os.getpid()
    journal.state['process']['start_ticks'] = 'invalid'
    assert journal.owned_pid() is None
    assert journal.reconcile()['state'] == 'recovering'


def test_transitions_persist_and_prevent_duplicate_start(tmp_path):
    journal = SessionJournal(tmp_path)
    run = journal.begin('test', {'seed': 7})
    with pytest.raises(RuntimeError): journal.begin('second', {})
    journal.attach(os.getpid())
    journal.transition('stopping')
    journal.transition('stopping')
    journal.transition('recovering')
    journal.transition('stopped')
    assert SessionJournal(tmp_path).snapshot()['state'] == 'stopped'
    assert (tmp_path/'experiments'/run/'execution.json').is_file()
    assert journal.begin('next', {}) != run


def test_invalid_transition_and_corruption_fail_closed(tmp_path):
    journal = SessionJournal(tmp_path)
    with pytest.raises(RuntimeError): journal.transition('completed')
    (tmp_path/'session.json').write_text('{broken')
    with pytest.raises(ValueError): SessionJournal(tmp_path)
    assert process_identity(-1) is None

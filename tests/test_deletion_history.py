import json
import os
from pathlib import Path
import subprocess
import sys
import pytest
from carla_safety_agent.deletion_history import DeletionHistory


@pytest.mark.parametrize('error,state', [(None,'confirmed'), ('snapshot timeout','needs_attention')])
def test_durable_intent_retains_backup(tmp_path,error,state):
    store=DeletionHistory(tmp_path/'history')
    backup=dict(scene_id='scene',version='version',stable_id='stable')
    op=store.begin(1,7,'static.prop.test',backup)
    assert json.loads(store.path(op).read_text())['state']=='attempting'
    restarted=DeletionHistory(store.root)
    row=restarted.finish(op,error)
    assert row['state']==state and row['backup']==backup
    with pytest.raises(ValueError):restarted.finish(op)


def test_invalid_backup_never_creates_intent(tmp_path):
    store=DeletionHistory(tmp_path/'history')
    with pytest.raises(ValueError):
        store.begin(1,7,'static.prop.test',dict(scene_id='../outside',version='v',stable_id='s'))
    assert not store.root.exists()


def test_listing_survives_restart_and_exposes_incomplete_rows(tmp_path):
    store=DeletionHistory(tmp_path/'history')
    first=store.begin(1,7,'prop',dict(scene_id='s',version='v',stable_id='id'))
    second=store.begin(1,8,'prop',dict(scene_id='s',version='v',stable_id='other'))
    store.finish(second)
    listing=DeletionHistory(store.root).list(1)
    assert listing['total']==2 and listing['truncated'] and listing['complete']
    assert listing['entries'][0]['operation_id']==second
    assert store.read(first)['state']=='attempting'
    store.path(first).write_text('{}')
    listing=store.list()
    assert not listing['complete'] and listing['warnings'][0]['operation_id']==first
    assert len(listing['entries'])==1


def test_linked_history_is_never_read(tmp_path):
    store=DeletionHistory(tmp_path/'history');store.root.mkdir()
    outside=tmp_path/'outside.json';outside.write_text('{}')
    (store.root/'linked.json').symlink_to(outside)
    listing=store.list()
    assert not listing['complete'] and listing['entries']==[]
    with pytest.raises(ValueError):store.list(True)
    with pytest.raises(ValueError):store.list(201)


def test_abrupt_writer_exit_leaves_inspectable_intent(tmp_path):
    # Actual subprocess exits without exception handling or Python finalizers.
    code = '''
import os, sys
from carla_safety_agent.deletion_history import DeletionHistory
store=DeletionHistory(sys.argv[1])
store.begin(1,7,'static.prop.test',dict(scene_id='s',version='v',stable_id='stable'))
os._exit(73)
'''
    env=dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]/'src'))
    result=subprocess.run([sys.executable,'-c',code,str(tmp_path/'history')],env=env,timeout=10)
    assert result.returncode==73
    restarted=DeletionHistory(tmp_path/'history')
    listing=restarted.list()
    assert listing['complete'] and listing['total']==1
    row=listing['entries'][0]
    assert row['state']=='attempting' and row['backup']['stable_id']=='stable'
    assert 'finished_at' not in row


@pytest.mark.parametrize('after_replace',[False,True])
def test_completion_write_failure_preserves_inspectable_state(tmp_path,monkeypatch,after_replace):
    import carla_safety_agent.deletion_history as module
    store=DeletionHistory(tmp_path/'history')
    op=store.begin(1,7,'prop',dict(scene_id='s',version='v',stable_id='stable'))
    original=module.atomic
    def fail(path,row):
        if after_replace:original(path,row)
        raise OSError('injected directory sync or write failure')
    monkeypatch.setattr(module,'atomic',fail)
    with pytest.raises(OSError):store.finish(op)
    row=DeletionHistory(store.root).read(op)
    assert row['state']==('confirmed' if after_replace else 'attempting')
    assert row['backup']==dict(scene_id='s',version='v',stable_id='stable')
    # A failed acknowledgement must not overwrite an already-published confirmation.
    if after_replace:
        with pytest.raises(ValueError):store.finish(op,'uncertain acknowledgement')
        assert store.read(op)['state']=='confirmed'

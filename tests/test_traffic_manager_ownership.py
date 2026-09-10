from pathlib import Path

import pytest

from carla_safety_agent.traffic_manager_ownership import (
    listening_inodes, require_unused_port, current_process_listener, require_stopped_manager)


def proc(tmp_path, rows=()):
    net=tmp_path/'self/net';net.mkdir(parents=True)
    (tmp_path/'self/fd').mkdir()
    header=' sl local_address rem_address st tx_queue rx_queue tr tm->when retrnsmt uid timeout inode\n'
    # Match real /proc/net/tcp field positions, not the header's visual columns.
    (net/'tcp').write_text(header+''.join(f'0: 00000000:1F72 00000000:0000 {state} 00000000:00000000 00:00000000 00000000 1000 0 {inode}\n' for state,inode in rows))
    (net/'tcp6').write_text(header)
    return tmp_path


def test_listener_must_belong_to_current_worker(tmp_path):
    root=proc(tmp_path,[('0A',123)])
    assert listening_inodes(8050,root)=={123}
    with pytest.raises(RuntimeError,match='already in use'):require_unused_port(8050,root)
    with pytest.raises(RuntimeError,match='not exclusively'):current_process_listener(8050,root)
    (root/'self/fd/5').symlink_to('socket:[123]')
    record=current_process_listener(8050,root)
    assert record['listener_inodes']==[123]
    with pytest.raises(RuntimeError,match='still has a listener'):require_stopped_manager(record,root)


def test_port_reuse_is_not_previous_ownership(tmp_path):
    root=proc(tmp_path,[('0A',456)])
    with pytest.raises(RuntimeError):
        require_stopped_manager({'port':8050,'listener_inodes':[123],'scope':'worker_local_listener'},root)


def test_closed_listener_and_time_wait_are_not_running_manager(tmp_path):
    root=proc(tmp_path,[('06',0)])
    require_unused_port(8050,root)
    require_stopped_manager({'port':8050,'listener_inodes':[123],'scope':'worker_local_listener'},root)


@pytest.mark.parametrize('port',[True,8000,0,65536,'8050'])
def test_wrong_port_rejected(tmp_path,port):
    with pytest.raises(ValueError):listening_inodes(port,tmp_path)


def test_missing_table_is_not_assumed_unused(tmp_path):
    with pytest.raises(OSError):require_unused_port(8050,tmp_path)


def test_mixed_listener_owners_are_rejected(tmp_path):
    root=proc(tmp_path,[('0A',123),('0A',456)])
    (root/'self/fd/5').symlink_to('socket:[123]')
    with pytest.raises(RuntimeError,match='not exclusively'):current_process_listener(8050,root)


@pytest.mark.parametrize('failure',['occupied','unowned',None])
def test_acquire_does_not_change_unproven_manager(monkeypatch,failure):
    from types import SimpleNamespace as NS
    import carla_safety_agent.traffic_manager_ownership as module
    events=[]
    def check(_):
        events.append('check')
        if failure=='occupied':raise RuntimeError('occupied')
    def proof(_):
        events.append('proof')
        if failure=='unowned':raise RuntimeError('unowned')
        return {'proof':True}
    manager=NS(set_synchronous_mode=lambda _:pytest.fail('Acquisition must not mutate sync mode'))
    client=NS(get_trafficmanager=lambda _:events.append('get') or manager)
    monkeypatch.setattr(module,'require_unused_port',check)
    monkeypatch.setattr(module,'current_process_listener',proof)
    if failure:
        with pytest.raises(RuntimeError):module.acquire_local_manager(client,8050)
    else:
        assert module.acquire_local_manager(client,8050)==(manager,{'proof':True})
    assert events==(['check'] if failure=='occupied' else ['check','get','proof'])

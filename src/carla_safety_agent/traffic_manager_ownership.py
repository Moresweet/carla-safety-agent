"""Linux-local listener evidence for a dedicated worker-hosted Traffic Manager.

Never connects to or resets another Traffic Manager. A dead worker's server
must have no listener before actor recovery proceeds; a reused port is not
assumed to belong to the previous worker.
"""
import os
from pathlib import Path

PORTS = {8050, 8051}


def listening_inodes(port, proc_root=Path('/proc')):
    if type(port) is not int or port not in PORTS:
        raise ValueError('Only dedicated studio Traffic Manager ports are supported')
    result=set()
    for name in ('tcp','tcp6'):
        lines=(Path(proc_root)/'self/net'/name).read_text().splitlines()
        if not lines or 'local_address' not in lines[0]:
            raise ValueError('Unrecognized Linux TCP table')
        for line in lines[1:]:
            fields=line.split()
            if len(fields)<10:
                raise ValueError('Incomplete Linux TCP entry')
            if fields[3]=='0A' and int(fields[1].rsplit(':',1)[1],16)==port:
                inode=int(fields[9])
                if inode<=0:
                    raise ValueError('Traffic Manager listener has no attributable inode')
                result.add(inode)
    return result


def require_unused_port(port, proc_root=Path('/proc')):
    if listening_inodes(port,proc_root):
        raise RuntimeError('Dedicated Traffic Manager port is already in use; refusing to attach or change it')


def current_process_listener(port, proc_root=Path('/proc')):
    listeners=listening_inodes(port,proc_root)
    own=set()
    for path in (Path(proc_root)/'self/fd').iterdir():
        try:
            target=os.readlink(path)
        except FileNotFoundError:
            continue  # Descriptor closed while enumerating; not ownership proof.
        if target.startswith('socket:[') and target.endswith(']'):
            own.add(int(target[8:-1]))
    if not listeners or not listeners.issubset(own):
        raise RuntimeError('Traffic Manager listener is not exclusively owned by this worker')
    return {'port':port,'listener_inodes':sorted(listeners),'scope':'worker_local_listener'}


def acquire_local_manager(client, port):
    require_unused_port(port)
    manager=client.get_trafficmanager(port)
    # Validate ownership before changing synchronous mode or registering actors.
    record=current_process_listener(port)
    return manager,record


def validate_manager_record(record):
    if (not isinstance(record,dict) or set(record)!={'port','listener_inodes','scope'} or
            record['scope']!='worker_local_listener' or not isinstance(record['listener_inodes'],list) or
            not record['listener_inodes'] or len(record['listener_inodes'])>16 or
            type(record['port']) is not int or record['port'] not in PORTS or
            any(type(i) is not int or i<=0 for i in record['listener_inodes']) or
            len(set(record['listener_inodes']))!=len(record['listener_inodes'])):
        raise ValueError('Invalid Traffic Manager ownership record')


def require_stopped_manager(record, proc_root=Path('/proc')):
    validate_manager_record(record)
    if listening_inodes(record['port'],proc_root):
        raise RuntimeError('Traffic Manager port still has a listener; refusing recovery even if the port was reused')

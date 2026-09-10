"""Test Linux listener ownership with our own temporary loopback socket, no CARLA."""
import json
import socket
import uuid
from pathlib import Path

from carla_safety_agent.traffic_manager_ownership import (
    require_unused_port,current_process_listener,require_stopped_manager)


def main():
    port=8051
    require_unused_port(port)
    record=None
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as listener:
        listener.bind(('127.0.0.1',port))
        listener.listen(1)
        record=current_process_listener(port)
        try:
            require_unused_port(port)
        except RuntimeError:
            pass
        else:
            raise AssertionError('In-use listener was not rejected')
        try:
            require_stopped_manager(record)
        except RuntimeError:
            pass
        else:
            raise AssertionError('Live listener was treated as stopped')
    require_stopped_manager(record)
    path=Path(__file__).resolve().parents[1]/'runs/validation'/('tm-listener-'+uuid.uuid4().hex+'.json')
    path.write_text(json.dumps({'state':'verified','record':record,
        'scope':'Real Linux proc listener ownership and close checks; not an actual Traffic Manager lifecycle'},indent=2))
    print(path,flush=True)


if __name__=='__main__':main()

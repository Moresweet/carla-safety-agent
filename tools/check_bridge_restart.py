"""Pre-restart check; unavailable/legacy status endpoints require manual review."""
import argparse
import os
import socket
import subprocess
from carla_safety_agent.restart_guard import verify_idle, verify_crash_restart
from regression_scene_versions import request


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--after-crash',action='store_true')
    args=parser.parse_args()
    session=request('session/status')['session']
    scheduler=request('batches/scheduler')['scheduler']
    if args.after_crash:
        native=subprocess.run(['pgrep','-x','UE4Editor'],capture_output=True,check=False)
        if native.returncode not in (0,1):raise RuntimeError('Could not determine native process state')
        try:
            with socket.create_connection(('127.0.0.1',int(os.environ.get('CARLA_PORT','2000'))),timeout=2):
                port_open=True
        except ConnectionRefusedError:
            port_open=False
        verify_crash_restart(session,scheduler,native.returncode==0,port_open)
    else:
        verify_idle(session,scheduler)
    print('Bridge restart gate passed; no live execution or active batch scheduler')

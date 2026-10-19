"""Bounded read-only real CARLA connection churn; no tick or world mutation."""
import concurrent.futures
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys
import time
import uuid
import argparse


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duration',type=int,default=0,help='Minimum sustained seconds, 0..600')
    args=parser.parse_args()
    if not 0<=args.duration<=600:parser.error('duration must be 0..600')
    root = Path(__file__).resolve().parents[1]
    log = Path('/home/moresweet/carla/Unreal/CarlaUE4/Saved/Logs/CarlaUE4.log')
    before = log.stat()
    offset = before.st_size
    def one(index):
        result = subprocess.run([sys.executable, '-m', 'carla_safety_agent.simulator_probe_worker',
                                 '127.0.0.1', '2000'], capture_output=True, text=True,
                                timeout=5, env=os.environ.copy())
        if result.returncode != 0:
            raise RuntimeError(result.stderr[-2000:])
        value = json.loads(result.stdout)
        if value.get('ok') is not True:
            raise ValueError('Invalid probe response')
        with socket.create_connection(('127.0.0.1', 2000), timeout=2) as client:
            if index % 2:
                client.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))
        return value['version']
    started = time.monotonic()
    versions=[];failure=None;final=None;rounds=0
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            while True:
                versions.extend(pool.map(one, range(200)))
                rounds+=1
                print(json.dumps({'rounds':rounds,'completed':len(versions),'elapsed_s':time.monotonic()-started}),flush=True)
                if time.monotonic()-started>=args.duration:break
        final = one(200)
    except Exception as error:
        failure=str(error)
    after = log.stat()
    if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino) or after.st_size < offset:
        failure='Engine log rotated during test; '+str(failure or '')
    with log.open('rb') as stream:
        stream.seek(offset)
        added = stream.read()
    failed = any(marker in added for marker in (b'Fatal error:', b'Critical error:', b'Unhandled Exception:'))
    report = {'passed': not failed and failure is None, 'completed_rpc_disconnect_pairs': len(versions)+(final is not None),
              'requested_duration_s':args.duration,'rounds':rounds,'error':failure,
              'workers': 4, 'elapsed_s': time.monotonic()-started,
              'versions': sorted(set(versions)), 'final_version': final,
              'new_fatal_log': failed, 'scope': 'version RPC and EOF/reset; not a model or long-route test'}
    out = root / 'runs/validation' / ('carla-rpc-disconnect-' + uuid.uuid4().hex + '.json')
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps({'receipt': str(out), **report}))
    if not report['passed']:
        raise RuntimeError('Disconnect test failed; inspect '+str(out))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Exercise real bridge GET handlers against a silent TCP simulator fixture.

No main-bridge startup/recovery, model, tick, scene write or dataset mutation.
Both HTTP and fake simulator ports are ephemeral and loopback-only.
"""
import argparse
import concurrent.futures
import json
import os
from pathlib import Path
import runpy
import socketserver
import threading
import time
from urllib.error import HTTPError
from urllib.request import urlopen
import uuid

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', required=True)
    args = parser.parse_args()
    if not args.dataset.startswith('capture-') or not all(c.isalnum() or c == '-' for c in args.dataset):
        raise ValueError('Expected an existing capture ID')
    rpc_started = threading.Event()
    release = threading.Event()

    class Silent(socketserver.BaseRequestHandler):
        def handle(self):
            self.request.settimeout(3)
            try:
                if self.request.recv(4096):
                    rpc_started.set()
                    release.wait(10)
            except OSError:
                pass

    class Fixture(socketserver.ThreadingTCPServer):
        daemon_threads = True

    with Fixture(('127.0.0.1', 0), Silent) as simulator:
        threading.Thread(target=simulator.serve_forever, daemon=True).start()
        os.environ['CARLA_PORT'] = str(simulator.server_address[1])
        bridge = runpy.run_path(str(ROOT/'tools/livery_bridge.py'))
        if bridge['SESSION'].snapshot()['state'] in ('preparing', 'running', 'stopping', 'recovering'):
            raise RuntimeError('Refuse validation while a real session is active')
        with bridge['ThreadingHTTPServer'](('127.0.0.1', 0), bridge['Handler']) as http:
            threading.Thread(target=http.serve_forever, daemon=True).start()
            base = f'http://127.0.0.1:{http.server_port}'

            def read(path):
                start = time.monotonic()
                try:
                    response = urlopen(base+path, timeout=5)
                except HTTPError as exc:
                    response = exc
                with response:
                    result = {'path': path, 'status': response.status, 'body': json.load(response)}
                result['seconds'] = time.monotonic()-start
                return result

            report = {'schema': 'offline-bridge-health/1', 'ok': False, 'fixture': 'accept TCP, never respond to CARLA RPC', 'dataset': args.dataset}
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    native = pool.submit(read, '/scene/state')
                    assert rpc_started.wait(3), 'Native child did not issue an RPC to the fixture'
                    assert not native.done(), 'Fault window ended before offline requests'
                    datasets = read('/datasets')
                    assert datasets['status'] == 200
                    assert any(d['run_id'] == args.dataset for d in datasets['body']['datasets'])
                    index = read('/datasets/index?run_id='+args.dataset)
                    assert index['status'] == 200 and index['body']['frames']
                    frame = index['body']['frames'][0]['frame']
                    sample = read(f'/datasets/frame?run_id={args.dataset}&frame={frame}')
                    assert sample['status'] == 200 and sample['body']['frame'] == frame
                    for item in (datasets, index, sample):
                        assert item['seconds'] < .75, item
                    unavailable = native.result(timeout=4)
                    assert unavailable['status'] == 503
                    assert 'readiness unavailable' in unavailable['body']['error']
                    assert unavailable['seconds'] < 3
                    cached = read('/scene/state')
                    assert cached['status'] == 503 and cached['seconds'] < .25
                    report.update(ok=True, offline_reads=[{k:v for k,v in item.items() if k != 'body'} for item in (datasets,index,sample)],
                                  native_failure=unavailable, cached_failure=cached)
            except Exception as exc:
                report['error'] = str(exc)
                raise
            finally:
                release.set()
                http.shutdown()
                simulator.shutdown()
                output = ROOT/'runs/validation'/('offline-bridge-health-'+uuid.uuid4().hex+'.json')
                output.parent.mkdir(parents=True, exist_ok=True)
                with output.open('x') as stream:
                    json.dump(report, stream, indent=2)
                print(output)
                print(json.dumps(report))


if __name__ == '__main__':
    main()

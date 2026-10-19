"""Bounded concurrent read-only requests against the deployed storage endpoint."""
import argparse
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen
from carla_safety_agent.owned_resources import durable_write


def read(path):
    try:
        with urlopen('http://127.0.0.1:8765/'+path, timeout=60) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        return error.code, json.load(error)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        raise ValueError('Receipt must be new')
    barrier = threading.Barrier(2)
    def concurrent(_):
        barrier.wait(timeout=5)
        return read('system/runtime-storage')
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(concurrent, range(2)))
    assert sorted(status for status, _ in results) == [200,409], results
    busy = next(value for status,value in results if status == 409)
    assert busy['code'] == 'runtime_storage_busy' and busy['ok'] is False
    status, after = read('system/runtime-storage')
    assert status == 200 and after['schema_version'] == 'runtime-storage/1'
    assert after['deletion_approved'] is False
    assert sum(row['allocated_bytes'] for row in after['categories']) == after['allocated_bytes']
    rejected, _ = read('system/runtime-storage?path=/tmp')
    assert rejected == 400
    durable_write(args.output, {'passed':True, 'concurrent_statuses':[s for s,_ in results],
        'busy':busy, 'after':after, 'path_override_status':rejected,
        'scope':'Deployed read-only overlap rejection and subsequent lock release; not cross-process global quota'}, exclusive=True)
    print(json.dumps({'passed':True,'statuses':[s for s,_ in results],'receipt':str(args.output)}))


if __name__ == '__main__':
    main()

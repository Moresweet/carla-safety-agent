"""Two read-only HTTP scans, followed by a retry; never modifies captures."""
import concurrent.futures
import json
import threading
import urllib.request
import urllib.error
import argparse
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('Receipt exists')
    barrier=threading.Barrier(2)
    def request(paired=False):
        if paired:barrier.wait(timeout=5)
        try:
            response=urllib.request.urlopen('http://127.0.0.1:8765/datasets/storage',timeout=60)
        except urllib.error.HTTPError as error:response=error
        with response:
            body=json.load(response)
            return {'status':response.code,'ok':body.get('ok'),'complete':body.get('complete'),
                    'recordings':len(body.get('recordings',[])),'error':body.get('error')}
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(request,True) for _ in range(2)]
        pair=[future.result() for future in futures]
    retry=request()
    passed=sorted(item['status'] for item in pair)==[200,409] and retry['status']==200 and retry['ok'] is True
    report={'passed':passed,'pair':pair,'retry':retry,'scope':'Live read-only bridge requests; no deletion or recording mutation'}
    with args.output.open('x') as stream:json.dump(report,stream,indent=2)
    print(json.dumps(report))
    if not passed:raise SystemExit('Concurrency assertion failed; inspect receipt')


if __name__=='__main__':main()

"""Compare deployed read-only batch reports with local validated ledgers."""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
from carla_safety_agent.experiment_report import summarize_queue
from carla_safety_agent.scene_store import read_json
from carla_safety_agent.owned_resources import durable_write


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        raise ValueError('Receipt must be new')
    root=Path(__file__).resolve().parents[1]
    rows=[]
    for path in sorted((root/'data/experiment-queues').glob('*/queue.json')):
        before=hashlib.sha256(path.read_bytes()).hexdigest()
        expected=summarize_queue(read_json(path,max_bytes=32*1024**2),
            {'rule-run':root/'runs/rule','run':root/'runs/uniad'})
        batch=path.parent.name
        with urlopen('http://127.0.0.1:8765/batches/report?'+urlencode({'batch_id':batch}),timeout=30) as response:
            actual=json.load(response)
        assert actual['ok'] is True and actual['batch_id']==batch, actual
        assert actual['report']==expected, batch
        assert hashlib.sha256(path.read_bytes()).hexdigest()==before, 'Ledger changed'
        rows.append({'batch_id':batch,'ledger_sha256':before,'jobs':expected['job_count'],
            'metric_errors':sum(bool(r.get('metrics_error')) for r in expected['rows'])})
    assert rows, 'No ledgers tested'
    durable_write(args.output,{'passed':True,'batches':rows,
        'scope':'Deployed read-only report equality; no new experiments or corruption of business data'},exclusive=True)
    print(json.dumps({'passed':True,'batches':len(rows),'jobs':sum(r['jobs'] for r in rows),'receipt':str(args.output)}))


if __name__=='__main__':main()

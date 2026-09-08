"""Verify completed batch metrics and every execution's saved capture offline."""
import argparse
import json
import subprocess
import sys
from carla_safety_agent.batch_catalog import BatchCatalog
from carla_safety_agent.experiment_report import summarize_queue
from carla_safety_agent.capture_identity import verify_capture_identity
from carla_safety_agent.session import SessionJournal
from regression_scene_versions import ROOT


def validate(batch_id):
    state = BatchCatalog(ROOT/'data/experiment-queues').read(batch_id)
    report = summarize_queue(state, {'rule-run': ROOT/'runs/rule', 'run': ROOT/'runs/uniad'})
    if not report['all_executions_completed']:
        raise ValueError('Batch is not fully completed')
    captures = {}
    for path in (ROOT/'.runtime/generated-scenarios').glob('capture-*/manifest.json'):
        manifest = json.loads(path.read_text())
        captures.setdefault(manifest.get('execution_id'), []).append(path.parent)
    verified = []
    for row in report['rows']:
        if not row.get('metrics') or row.get('metrics_error'):
            raise ValueError('Execution metrics are not verified: '+row['job_id'])
        datasets = captures.get(row['execution_id'], [])
        if not datasets:
            raise ValueError('Missing execution capture: '+row['execution_id'])
        for dataset in datasets:
            verify_capture_identity(dataset, SessionJournal(ROOT/'data').read_execution(row['execution_id']))
            subprocess.run([sys.executable, str(ROOT/'tools/validate_capture_dataset.py'), str(dataset)], check=True)
        verified.append({'execution_id': row['execution_id'], 'attempt_count': row['attempt_count'],
                         'datasets': [str(p) for p in datasets]})
    return {'batch_id': batch_id, 'verified': verified, 'passed': True,
            'scope': 'Completed metrics and capture format; not driving success or simulator cleanup'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('batch_id')
    print(json.dumps(validate(parser.parse_args().batch_id)))

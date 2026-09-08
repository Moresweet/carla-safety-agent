"""Verify one native model execution and all associated capture archives."""
import argparse
import json
import subprocess
import sys
from carla_safety_agent.capture_identity import verify_capture_identity
from carla_safety_agent.experiment_report import verified_rule_metrics
from carla_safety_agent.session import SessionJournal
from regression_scene_versions import ROOT


def validate(run_id):
    record = SessionJournal(ROOT/'data').read_execution(run_id)
    if record.get('kind') != 'run' or record.get('returncode') != 0 or record.get('error'):
        raise ValueError('Native model execution has not exited successfully')
    metrics = verified_rule_metrics(record, ROOT/'runs/uniad')
    captures = [p.parent for p in (ROOT/'.runtime/generated-scenarios').glob('capture-*/manifest.json')
                if json.loads(p.read_text()).get('execution_id') == run_id]
    if not captures:
        raise ValueError('No model capture archives found')
    for dataset in captures:
        verify_capture_identity(dataset, record)
        manifest = json.loads((dataset/'manifest.json').read_text())
        if manifest.get('family') != 'model-input' or manifest.get('input_archive') != 'model_input.npz':
            raise ValueError('Capture does not contain actual model inputs')
        subprocess.run([sys.executable, str(ROOT/'tools/validate_capture_dataset.py'), str(dataset)], check=True)
    return {'execution_id': run_id, 'algorithm': record['configuration']['request']['algorithm'],
            'metrics': metrics, 'datasets': [str(p) for p in captures],
            'verified': True, 'scope': 'Execution, scenario identity and model input capture; not native cleanup'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('execution_id')
    print(json.dumps(validate(parser.parse_args().execution_id)))

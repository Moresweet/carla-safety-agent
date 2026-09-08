"""Create a pending queue from a verified matrix archive, without dispatching."""
import argparse
import hashlib
import json
from pathlib import Path
from carla_safety_agent.experiment_matrix import canonical, compile_matrix
from carla_safety_agent.experiment_queue import ExperimentQueue


def create_queue(plan_path, queue_root):
    path = Path(plan_path)
    if path.is_symlink() or path.stat().st_size > 32*1024*1024:
        raise ValueError('Invalid matrix archive path or size')
    payload = path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if path.name != f'matrix-{digest}.json':
        raise ValueError('Matrix archive content identity mismatch')
    document = json.loads(payload)
    compiled = compile_matrix(document['dimensions'])
    if document != compiled or canonical(compiled) != payload:
        raise ValueError('Matrix jobs differ from declared dimensions')
    state = ExperimentQueue(queue_root).create(document['dimensions'])
    return {'queue': str(Path(queue_root).resolve()), 'plan_sha256': state['plan_sha256'],
            'job_count': len(state['jobs']), 'dispatched': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan', type=Path)
    parser.add_argument('queue', type=Path)
    args = parser.parse_args()
    print(json.dumps(create_queue(args.plan, args.queue)))


if __name__ == '__main__': main()

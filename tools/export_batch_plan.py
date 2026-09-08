"""Export a verified batch's immutable plan; never copy execution reservations.

This transfers matrix configuration, not assets, datasets, model weights or
machine dependencies. Import creates a fresh pending queue, not a resumed run.
"""
import argparse
import json
from pathlib import Path
from carla_safety_agent.batch_catalog import BatchCatalog
from carla_safety_agent.experiment_matrix import save_matrix


def export_plan(catalog_root, batch_id, output):
    state = BatchCatalog(catalog_root).read(batch_id)
    path, digest = save_matrix(output, state['plan']['dimensions'])
    if digest != state['plan_sha256']:
        raise ValueError('Exported plan identity differs from batch')
    return {'path': str(path.resolve()), 'plan_sha256': digest,
            'job_count': len(state['jobs']), 'execution_history_included': False,
            'assets_included': False, 'dispatched': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('batch_id')
    parser.add_argument('--catalog', type=Path,
                        default=Path(__file__).resolve().parents[1]/'data/experiment-queues')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export_plan(args.catalog, args.batch_id, args.output)))


if __name__ == '__main__':
    main()

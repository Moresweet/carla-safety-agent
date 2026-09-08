"""Compile a local experiment matrix without starting any evaluation."""
import argparse
import json
from pathlib import Path
from carla_safety_agent.experiment_matrix import save_matrix


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dimensions', type=Path)
    parser.add_argument('--output', type=Path, default=Path('data/experiment-matrices'))
    args = parser.parse_args()
    if args.dimensions.stat().st_size > 8*1024*1024:
        parser.error('Input exceeds 8 MiB')
    path, digest = save_matrix(args.output, json.loads(args.dimensions.read_text()))
    print(json.dumps({'path': str(path.resolve()), 'sha256': digest,
                      'execution_status': 'not_started'}))


if __name__ == '__main__':
    main()

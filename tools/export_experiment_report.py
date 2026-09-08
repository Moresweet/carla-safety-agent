"""Export a content-addressed JSON batch report; never start a simulation."""
import argparse
import hashlib
from pathlib import Path
from carla_safety_agent.experiment_matrix import canonical
from carla_safety_agent.experiment_queue import ExperimentQueue
from carla_safety_agent.experiment_report import summarize_queue, compare_variants


def export_report(queue_root, results_root, output_root, comparison=None):
    report = summarize_queue(ExperimentQueue(queue_root).read(), results_root)
    if comparison:
        report['comparison'] = compare_variants(report, *comparison)
    payload = canonical(report)
    digest = hashlib.sha256(payload).hexdigest()
    root = Path(output_root); root.mkdir(parents=True, exist_ok=True)
    path = root/f'report-{digest}.json'
    try:
        with path.open('xb') as stream: stream.write(payload)
    except FileExistsError:
        if path.is_symlink() or path.read_bytes() != payload:
            raise ValueError('Existing report differs from its content identity')
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('queue', type=Path)
    parser.add_argument('--results-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--compare', nargs=3, metavar=('AXIS', 'BASELINE', 'CANDIDATE'))
    args = parser.parse_args()
    print(export_report(args.queue, args.results_root, args.output, args.compare).resolve())


if __name__ == '__main__': main()

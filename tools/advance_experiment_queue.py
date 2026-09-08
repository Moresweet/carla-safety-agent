"""Advance one local batch scheduler step; may start one real CARLA rule run."""
import argparse
import json
from pathlib import Path
from carla_safety_agent.experiment_dispatch import advance_queue
from carla_safety_agent.experiment_queue import ExperimentQueue
from carla_safety_agent.session import SessionJournal
from regression_scene_versions import ROOT, request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('queue', type=Path)
    control = parser.add_mutually_exclusive_group()
    control.add_argument('--pause', action='store_true', help='Pause new claims; do not stop the current simulation')
    control.add_argument('--resume', action='store_true', help='Allow future claims; does not itself start a run')
    args = parser.parse_args()
    queue = ExperimentQueue(args.queue)
    if args.pause or args.resume:
        result = queue.set_paused(args.pause)
    else:
        result = advance_queue(queue, SessionJournal(ROOT/'data'),
                               ROOT/'.runtime/generated-scenarios', request)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__': main()

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
    args = parser.parse_args()
    result = advance_queue(ExperimentQueue(args.queue), SessionJournal(ROOT/'data'),
                           ROOT/'.runtime/generated-scenarios', request)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__': main()

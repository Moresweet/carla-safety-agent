"""Explicitly run a saved batch serially through the local bridge.

Ctrl-C stops scheduling, not the current simulation. Re-run to reconcile and
continue; no automatic failed-job retry or ambiguous reservation reclamation.
"""
import argparse
import json
import signal
import threading
from carla_safety_agent.batch_runner import run_batch
from carla_safety_agent.scene_store import identifier
from regression_scene_versions import request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('batch_id')
    args = parser.parse_args()
    identifier(args.batch_id)
    cancelled = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: cancelled.set())
    signal.signal(signal.SIGTERM, lambda *_: cancelled.set())
    result = run_batch(
        lambda: request('batches/control', {'batch_id': args.batch_id, 'action': 'advance'}),
        lambda: cancelled.wait(1), cancelled=cancelled.is_set,
        observe=lambda step: print(json.dumps(step), flush=True))
    print(json.dumps(result), flush=True)
    return 0 if result['state'] == 'completed' else 2


if __name__ == '__main__':
    raise SystemExit(main())

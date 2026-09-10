"""Inspect explicitly configured runtime paths, without running their programs."""
import argparse
import json
import os
from carla_safety_agent.runtime_paths import diagnose_paths

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scope', choices=('native', 'all'), default='all')
    args = parser.parse_args()
    report = diagnose_paths(os.environ, args.scope)
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report['paths_present'] else 2)

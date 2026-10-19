"""Manage explicit keep markers only; never deletes capture files."""
import argparse
import json
from pathlib import Path
from carla_safety_agent.capture_retention import CaptureRetention


def main():
    repo = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('list','keep','unkeep'))
    parser.add_argument('--run-id')
    parser.add_argument('--reason')
    parser.add_argument('--expected-revision', type=int)
    args = parser.parse_args()
    store = CaptureRetention(repo/'data', repo/'.runtime/generated-scenarios')
    if args.action == 'list':
        result = store.snapshot()
    else:
        if None in (args.run_id, args.reason, args.expected_revision):
            parser.error('Changes require --run-id, --reason and --expected-revision')
        result = store.set_keep(args.run_id, args.action == 'keep', args.reason,
                                expected_revision=args.expected_revision)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__': main()

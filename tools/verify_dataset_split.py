"""Read-only check of a saved split against the current recording metadata."""
import argparse
import json
from pathlib import Path

from carla_safety_agent.dataset_split import verify_saved_split


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('split', type=Path)
    parser.add_argument('--dataset-root', required=True, type=Path)
    args = parser.parse_args()
    result = verify_saved_split(json.loads(args.split.read_text()), args.dataset_root)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()

"""Register an immutable copy of an explicitly selected metadata-verified split.

Does not move recordings, infer scene grouping, or approve deletion.
"""
import argparse
import json
from pathlib import Path
from carla_safety_agent.split_registry import register_split


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('split', type=Path)
    parser.add_argument('--dataset-root', type=Path, default=root/'.runtime/generated-scenarios')
    parser.add_argument('--registry', type=Path, default=root/'data/dataset-splits')
    args = parser.parse_args()
    print(json.dumps(register_split(args.split, args.registry, args.dataset_root), ensure_ascii=False))


if __name__ == '__main__':
    main()

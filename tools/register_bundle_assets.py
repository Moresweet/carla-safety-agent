"""Explicitly import bundled assets to Unreal; write a NEW remapped bundle, never restore the world."""
import argparse
import json
from pathlib import Path
from carla_safety_agent.bundle_registration import register_bundle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--execute-unreal-import', action='store_true', required=True)
    args = parser.parse_args()
    print(json.dumps(register_bundle(args.archive, args.project, args.output,
                                    execute=args.execute_unreal_import), ensure_ascii=False, indent=2))


if __name__ == '__main__': main()

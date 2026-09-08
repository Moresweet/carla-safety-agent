"""Offline portable scenes/textures. Does not restore a live CARLA world."""
import argparse
import json
from pathlib import Path

from carla_safety_agent.project_bundle import export_bundle, import_bundle, read_bundle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    export = commands.add_parser('export')
    export.add_argument('--project', type=Path, required=True)
    export.add_argument('--scene', action='append', required=True)
    export.add_argument('--output', type=Path, required=True)
    inspect = commands.add_parser('inspect')
    inspect.add_argument('archive', type=Path)
    load = commands.add_parser('import')
    load.add_argument('archive', type=Path)
    load.add_argument('--destination-parent', type=Path, required=True)
    args = parser.parse_args()
    if args.action == 'export':
        manifest = export_bundle(args.project/'data/scenes', args.project/'data', args.scene, args.output)
        result = {'archive': str(args.output.resolve()), 'manifest': manifest}
    elif args.action == 'inspect':
        manifest, _ = read_bundle(args.archive)
        result = {'manifest': manifest, 'dependency_availability': 'not_checked'}
    else:
        folder = import_bundle(args.archive, args.destination_parent)
        result = {'directory': str(folder.resolve()), 'live_world_modified': False,
                  'dependency_availability': 'not_checked'}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

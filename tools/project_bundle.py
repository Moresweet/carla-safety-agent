"""Offline portable scenes/textures. Does not restore a live CARLA world."""
import argparse
import json
from pathlib import Path

from carla_safety_agent.project_bundle import export_bundle, import_bundle, read_bundle, prepare_generated_assets


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    export = commands.add_parser('export')
    export.add_argument('--project', type=Path, required=True)
    export.add_argument('--scene', action='append', required=True)
    export.add_argument('--output', type=Path, required=True)
    export.add_argument('--include-material-previews', action='store_true')
    export.add_argument('--generated-asset', action='append', default=[], metavar='BLUEPRINT=PACKAGE',
                        help='Explicit source-package binding; cover all generated blueprints in scene history')
    inspect = commands.add_parser('inspect')
    inspect.add_argument('archive', type=Path)
    doctor = commands.add_parser('doctor')
    doctor.add_argument('archive', type=Path)
    doctor.add_argument('--project', type=Path, required=True)
    doctor.add_argument('--host', default='127.0.0.1')
    doctor.add_argument('--port', type=int, default=2000)
    stage = commands.add_parser('stage')
    stage.add_argument('archive', type=Path)
    stage.add_argument('--project', type=Path, required=True)
    load = commands.add_parser('import')
    load.add_argument('archive', type=Path)
    load.add_argument('--destination-parent', type=Path, required=True)
    prepare = commands.add_parser('prepare-assets')
    prepare.add_argument('archive', type=Path)
    prepare.add_argument('--project', type=Path, required=True)
    args = parser.parse_args()
    if args.action == 'export':
        bindings = {}
        for value in args.generated_asset:
            blueprint, separator, package = value.partition('=')
            if not separator or not blueprint or not package or blueprint in bindings:
                parser.error('Each --generated-asset needs a unique BLUEPRINT=PACKAGE binding')
            bindings[blueprint] = Path(package)
        manifest = export_bundle(args.project/'data/scenes', args.project/'data', args.scene, args.output,
                                 include_material_previews=args.include_material_previews,
                                 generated_assets=bindings if args.generated_asset else None)
        result = {'archive': str(args.output.resolve()), 'manifest': manifest}
    elif args.action == 'inspect':
        manifest, _ = read_bundle(args.archive)
        result = {'manifest': manifest, 'dependency_availability': 'not_checked'}
    elif args.action == 'prepare-assets':
        result = prepare_generated_assets(args.archive, args.project)
    elif args.action == 'stage':
        import uuid
        import shutil
        read_bundle(args.archive)
        folder = args.project/'data/project-bundles'; folder.mkdir(parents=True, exist_ok=True)
        bundle_id = uuid.uuid4().hex
        output = folder/(bundle_id+'.zip')
        with args.archive.open('rb') as source, output.open('xb') as destination:
            shutil.copyfileobj(source, destination)
        read_bundle(output)
        result = {'bundle_id': bundle_id, 'archive': str(output.resolve()), 'live_world_modified': False}
    elif args.action == 'doctor':
        from carla_safety_agent.bundle_diagnostics import diagnose
        import carla
        manifest, _ = read_bundle(args.archive)
        client = carla.Client(args.host, args.port); client.set_timeout(10)
        result = diagnose(manifest, client, args.project/'data')
    else:
        folder = import_bundle(args.archive, args.destination_parent)
        result = {'directory': str(folder.resolve()), 'live_world_modified': False,
                  'dependency_availability': 'not_checked'}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

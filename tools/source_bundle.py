"""Export, verify or restore committed source. Never install or execute restored code."""
import argparse
import json
from carla_safety_agent.source_bundle import export_source, verify_source, restore_source, source_export_status

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    status = commands.add_parser('status')
    status.add_argument('--project', default='.')
    export = commands.add_parser('export')
    export.add_argument('--project', default='.')
    export.add_argument('--output', required=True)
    export.add_argument('--require-current', action='store_true',
                        help='Refuse before writing if selected source has uncommitted changes; does not include dependencies/runtime')
    verify = commands.add_parser('verify')
    verify.add_argument('archive')
    restore = commands.add_parser('restore')
    restore.add_argument('archive')
    restore.add_argument('--destination', required=True, help='New directory; existing paths are refused')
    args = parser.parse_args()
    if args.action == 'status':
        result = source_export_status(args.project)
    elif args.action == 'export':
        result = export_source(args.project, args.output, require_current=args.require_current)
    elif args.action == 'restore':
        result = restore_source(args.archive, args.destination)
    else:
        result = verify_source(args.archive)
    print(json.dumps(result, indent=2))

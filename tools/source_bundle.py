"""Export or verify a local committed-source ZIP. Does not install or execute it."""
import argparse
import json
from carla_safety_agent.source_bundle import export_source, verify_source

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    export = commands.add_parser('export')
    export.add_argument('--project', default='.')
    export.add_argument('--output', required=True)
    verify = commands.add_parser('verify')
    verify.add_argument('archive')
    args = parser.parse_args()
    result = export_source(args.project, args.output) if args.action == 'export' else verify_source(args.archive)
    print(json.dumps(result, indent=2))

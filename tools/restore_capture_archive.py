"""Restore a verified archive into a new isolated directory, without replacing recordings."""
import argparse
import json
from carla_safety_agent.capture_archive import restore_capture_archive

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('archive')
parser.add_argument('--destination-parent',required=True)
args=parser.parse_args()
print(json.dumps(restore_capture_archive(args.archive,args.destination_parent),ensure_ascii=False,indent=2))

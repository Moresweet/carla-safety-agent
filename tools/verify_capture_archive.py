"""Verify a standalone recording archive, without extracting or deleting files."""
import argparse
import json
from carla_safety_agent.capture_archive import verify_capture_archive

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('archive')
args=parser.parse_args()
receipt=verify_capture_archive(args.archive)
print(json.dumps({'verified':True,'run_id':receipt['source_run_id'],'files':len(receipt['files']),
                  'bytes':receipt['source_bytes'],'scope':'Archive integrity only; not raw sensor quality or driving success'}))

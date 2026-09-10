"""Offline recovery to a separate directory; source captures are never modified."""
import argparse
import json
from pathlib import Path
import sys
from carla_safety_agent.capture_recovery import recover_capture,require_inactive_execution,inventory
from carla_safety_agent.scene_store import identifier

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--confirm-copy',action='store_true',help='Create a new recovery copy after inspection')
    parser.add_argument('--install-replay',action='store_true',help='Publish the verified new copy to the local playback catalog')
    args=parser.parse_args();identifier(args.run_id)
    if args.install_replay and not args.confirm_copy:parser.error('--install-replay requires --confirm-copy')
    root=ROOT/'.runtime/generated-scenarios';source=root/args.run_id
    if source.is_symlink() or source.resolve().parent!=root.resolve():raise ValueError('Invalid source path')
    manifest=json.loads((source/'manifest.json').read_text())
    if manifest.get('run_id')!=args.run_id:raise ValueError('Source dataset identity mismatch')
    def inactive():require_inactive_execution(ROOT/'data',manifest['execution_id'])
    inactive()
    if not args.confirm_copy:
        files,size=inventory(source)
        print(json.dumps({'source':args.run_id,'bytes':size,'files':len(files),'source_modified':False,
                          'status':manifest['status'],'next':'Use --confirm-copy to create an audited copy'}));return
    destination=ROOT/'.runtime/capture-recovery';destination.mkdir(exist_ok=True)
    output=recover_capture(source,destination,ROOT/'tools/validate_capture_dataset.py',sys.executable,inactive)
    if args.install_replay:
        inactive()
        published=root/output.name
        if published.exists():raise ValueError('Recovery destination already exists; refusing overwrite')
        output.rename(published);output=published
    print(json.dumps({'recovered':str(output),'source_modified':False,
                      'installed_for_replay':args.install_replay,
                      'note':'Recovered subset, not a complete capture; training split admission remains disabled'}))


if __name__=='__main__':main()

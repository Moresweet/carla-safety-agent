"""Create a verified archive of one inactive recording, preserving its source."""
import argparse
import json
from pathlib import Path
from carla_safety_agent.capture_archive import archive_capture
from carla_safety_agent.capture_recovery import require_inactive_execution
from carla_safety_agent.scene_store import identifier,read_json


def main():
    repo=Path(__file__).resolve().parents[1]
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    source=repo/'.runtime/generated-scenarios'/identifier(args.run_id)
    manifest=read_json(source/'manifest.json',max_bytes=8*1024**2)
    execution=identifier(manifest.get('execution_id'))
    result=archive_capture(source,args.output,lambda:require_inactive_execution(repo/'data',execution))
    print(json.dumps({key:value for key,value in result.items() if key!='files'},ensure_ascii=False,indent=2))


if __name__=='__main__':main()

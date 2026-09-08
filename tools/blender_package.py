"""Pack or prepare Blender assets without executing Blender or Unreal."""
import argparse
import json
from pathlib import Path
from carla_safety_agent.blender_package import export_asset, import_asset, read_asset


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='action',required=True)
    export=commands.add_parser('export')
    export.add_argument('folder',type=Path);export.add_argument('output',type=Path)
    export.add_argument('--color',type=float,nargs=4,required=True)
    export.add_argument('--roughness',type=float,required=True)
    load=commands.add_parser('import');load.add_argument('archive',type=Path)
    load.add_argument('--project',type=Path,required=True)
    inspect=commands.add_parser('inspect');inspect.add_argument('archive',type=Path)
    args=parser.parse_args()
    if args.action=='export': result=export_asset(args.folder,args.output,{'color':args.color,'roughness':args.roughness})
    elif args.action=='import': result=import_asset(args.archive,args.project)
    else: result=read_asset(args.archive)[0]
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()

"""Export or verify relocated model identities without packaging any weights."""
import argparse
import json
from pathlib import Path

from carla_safety_agent.benchmark_catalog import algorithm_catalog
from carla_safety_agent.runtime_reference import export_reference, verify_reference


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='action',required=True)
    export=commands.add_parser('export')
    export.add_argument('--zoo',type=Path,required=True)
    export.add_argument('--tcp-zoo',type=Path,required=True)
    export.add_argument('--model',action='append',required=True)
    export.add_argument('--output',type=Path,required=True)
    verify=commands.add_parser('verify')
    verify.add_argument('reference',type=Path)
    verify.add_argument('--root',action='append',default=[],metavar='ALIAS=DIRECTORY')
    args=parser.parse_args()
    if args.action=='export':
        document=export_reference(algorithm_catalog(args.zoo,args.tcp_zoo),args.model,
                                  {'zoo':args.zoo,'tcp_zoo':args.tcp_zoo})
        with args.output.open('x') as stream:json.dump(document,stream,indent=2)
        print(json.dumps({'output':str(args.output),'files':len(document['files']),'weights_included':False}))
    else:
        if args.reference.stat().st_size>1024*1024:parser.error('Reference exceeds 1 MiB')
        roots={}
        for value in args.root:
            alias,separator,path=value.partition('=')
            if not separator or not path or alias in roots:parser.error('Use unique ALIAS=DIRECTORY roots')
            roots[alias]=Path(path)
        result=verify_reference(json.loads(args.reference.read_text()),roots)
        print(json.dumps(result,indent=2))
        if not result['ok']:raise SystemExit(1)


if __name__=='__main__':main()

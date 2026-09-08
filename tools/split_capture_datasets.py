"""Write a split manifest from explicit run_id/scene_group records; never move data."""
import argparse
import json
from pathlib import Path
from carla_safety_agent.dataset_split import split_runs


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('input',type=Path,help='JSON array of run_id and scene_group records')
    parser.add_argument('output',type=Path)
    parser.add_argument('--seed',type=int,default=7)
    parser.add_argument('--ratios',type=float,nargs=3,default=(.8,.1,.1))
    args=parser.parse_args()
    records=json.loads(args.input.read_text())
    if not isinstance(records,list): raise ValueError('Expected an array of run records')
    result=split_runs(records,args.ratios,args.seed)
    # Exclusive creation protects a previously approved split from accidental replacement.
    with args.output.open('x') as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2,allow_nan=False)
    print(f'Saved {result["run_count"]} runs in {result["group_count"]} scene groups')


if __name__=='__main__': main()

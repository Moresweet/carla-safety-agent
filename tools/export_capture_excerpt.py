"""Explicit local diagnostic-window export; original capture is never modified."""
import argparse
import json
import time
import uuid
from pathlib import Path
from carla_safety_agent.excerpt_service import ExcerptService


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id');parser.add_argument('--frame',type=int,required=True)
    parser.add_argument('--before',type=float,default=2);parser.add_argument('--after',type=float,default=2)
    parser.add_argument('--confirm-copy',action='store_true',required=True)
    args=parser.parse_args();root=Path(__file__).resolve().parents[1]
    service=ExcerptService(root/'.runtime/generated-scenarios',root/'.runtime/dataset-excerpts',root/'data',
        root/'tools/validate_capture_dataset.py','/home/moresweet/Data/e2e/miniconda3/envs/uniad-cu128/bin/python')
    request_id=uuid.uuid4().hex
    result=service.start({'run_id':args.run_id,'request_id':request_id,'frame':args.frame,
        'before_s':args.before,'after_s':args.after,'confirmed':True})
    print(json.dumps(result),flush=True)
    while result['state']=='running':
        time.sleep(.5);result=service.status(request_id)
    print(json.dumps(result),flush=True)
    if result['state']!='ready':raise RuntimeError('Excerpt was not published; inspect retained job evidence')


if __name__=='__main__':main()

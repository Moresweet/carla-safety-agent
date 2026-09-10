"""Add an exported UV preview catalog; refuses conflicting existing targets."""
import argparse
import json
from carla_safety_agent.material_catalog_merge import merge_preview_catalog


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source')
    parser.add_argument('--data-root',required=True)
    args=parser.parse_args()
    print(json.dumps(merge_preview_catalog(args.source,args.data_root)))

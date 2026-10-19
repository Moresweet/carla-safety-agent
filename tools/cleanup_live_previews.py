"""Explicit idle-only cleanup of known live preview cache, not recordings."""
import argparse
import hashlib
import subprocess
import sys
from pathlib import Path
from regression_scene_versions import ROOT
from carla_safety_agent.capture_quota import capture_write_lock
from carla_safety_agent.live_preview_cache import prune_previews
from carla_safety_agent.owned_resources import durable_write


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true', required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    if args.receipt.exists() or args.receipt.is_symlink():
        raise ValueError('Receipt must be new')
    live = ROOT/'.runtime/evaluation-control/capture'
    with capture_write_lock(live):
        subprocess.run([sys.executable, str(ROOT/'tools/check_bridge_restart.py')],
                       cwd=ROOT, check=True)
        before = (live/'latest.json').read_bytes()
        durable_write(args.receipt, {'state': 'started', 'target': str(live/'frames'),
            'latest_sha256': hashlib.sha256(before).hexdigest(),
            'policy': 'Known preview files only; current + newest six total and 60s grace; no saved recordings'}, exclusive=True)
        result = prune_previews(live)
        assert (live/'latest.json').read_bytes() == before
        durable_write(args.receipt, {'state': 'completed', 'target': str(live/'frames'),
            'latest_sha256': hashlib.sha256(before).hexdigest(), **result})
    print(args.receipt.read_text())


if __name__ == '__main__':
    main()

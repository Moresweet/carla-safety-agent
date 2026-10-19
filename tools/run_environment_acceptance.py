"""Produce fresh browser UV evidence and verify three native environment fixtures."""
import json
import subprocess
import sys
from pathlib import Path

NODE = '/home/moresweet/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node'
ROOT = Path(__file__).resolve().parents[1]

if __name__ == '__main__':
    for fixture, name in [('gas-station', 'SM_GasStation01_13'), ('bench', 'SM_Bench01_123'), ('road', 'Road_Road_Town04_1')]:
        browser = subprocess.run([NODE, 'tools/browser_reviewed_models.mjs', '--material-name', name,
            '--texture', str(ROOT / 'runs/validation/material-slots-20260908/uv-calibration.png'),
            '--uv-convention'], text=True, capture_output=True)
        print(browser.stdout, flush=True)
        print(browser.stderr, file=sys.stderr, flush=True)
        if browser.returncode:
            raise SystemExit(browser.returncode)
        evidence = json.loads(browser.stdout.strip().splitlines()[-1])
        subprocess.run([sys.executable, 'tools/regression_environment_uv.py', '--fixture', fixture,
            '--atlas', str(Path(evidence['output']) / 'material-atlas.png')], check=True)

"""Time-limited, isolated raw-capture audit; never connects to the simulator."""
import os
from pathlib import Path
import subprocess
import time


def audit_capture(dataset, validator, python, *, timeout=300):
    """Return evidence from this scan, not a permanent certification of mutable data."""
    started = time.time()
    environment = dict(os.environ)
    environment.pop('PYTHONOPTIMIZE', None)
    environment['PYTHONPATH'] = str(Path(validator).resolve().parents[1] / 'src')
    try:
        result = subprocess.run(
            [str(python), str(validator), str(Path(dataset).resolve())],
            env=environment, capture_output=True, text=True, timeout=timeout,
            check=False,
        )
        state = 'passed' if result.returncode == 0 else 'failed'
        detail = (result.stdout + '\n' + result.stderr).strip()[-12000:]
        returncode = result.returncode
    except subprocess.TimeoutExpired:
        state, detail, returncode = 'incomplete', 'Validation exceeded the time limit', None
    except OSError as error:
        state, detail, returncode = 'incomplete', str(error), None
    return {'schema_version': 'carla-capture-quality/1', 'state': state,
            'started_at_unix': started, 'finished_at_unix': time.time(),
            'returncode': returncode, 'detail': detail,
            'scope': 'Raw sensor files and saved input consistency; not driving safety or semantic ground-truth accuracy.',
            'freshness': 'Result applies to files read during this scan; later modifications require another scan.'}

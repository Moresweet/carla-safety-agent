"""Time-limited, isolated raw-capture audit; never connects to the simulator."""
import os
import json
from pathlib import Path
import subprocess
import time


def audit_capture(dataset, validator, python, *, timeout=300, pass_fds=()):
    """Return evidence from this scan, not a permanent certification of mutable data."""
    started = time.time()
    problem_frame = None
    environment = dict(os.environ)
    environment.pop('PYTHONOPTIMIZE', None)
    environment['PYTHONPATH'] = str(Path(validator).resolve().parents[1] / 'src')
    try:
        result = subprocess.run(
            [str(python), str(validator), str(Path(dataset).resolve())],
            env=environment, capture_output=True, text=True, timeout=timeout,
            check=False, pass_fds=pass_fds,
        )
        state = 'passed' if result.returncode == 0 else 'failed'
        detail = (result.stdout + '\n' + result.stderr).strip()[-12000:]
        returncode = result.returncode
        reason_code = None if state == 'passed' else 'validation_failed'
        # Only the validator's explicit protocol line can specialize a failure;
        # tracebacks and dataset strings are never used as machine evidence.
        lines = [line for line in result.stdout.splitlines() if line.startswith('CSA_CAPTURE_QUALITY=')]
        if state == 'failed' and len(lines) == 1:
            try:
                value = json.loads(lines[0].split('=',1)[1])
                if value == {'schema_version':'capture-quality-reason/1','reason_code':'no_samples'}:
                    reason_code = 'no_samples'
                elif (isinstance(value,dict) and set(value)=={'schema_version','reason_code','frame'}
                      and value['schema_version']=='capture-quality-reason/1'
                      and value['reason_code']=='invalid_ego_pose'
                      and type(value['frame']) is int and 0<=value['frame']<=9007199254740991):
                    reason_code, problem_frame = 'invalid_ego_pose', value['frame']
            except ValueError:
                pass
    except subprocess.TimeoutExpired:
        state, detail, returncode = 'incomplete', 'Validation exceeded the time limit', None
        reason_code = 'validation_timeout'
    except OSError as error:
        state, detail, returncode = 'incomplete', str(error), None
        reason_code = 'validator_unavailable'
    return {'schema_version': 'carla-capture-quality/1', 'state': state,
            'started_at_unix': started, 'finished_at_unix': time.time(),
            'returncode': returncode, 'detail': detail, 'reason_code':reason_code,
            'problem_frame': problem_frame,
            'scope': 'Raw sensor files and saved input consistency; not driving safety or semantic ground-truth accuracy.',
            'freshness': 'Result applies to files read during this scan; later modifications require another scan.'}

"""Session-owned rule executor; never launch without a verified studio session."""
import os
import math
import signal
import time
from pathlib import Path

from carla_safety_agent.carla_adapter import CarlaAdapter, RuleRunCancelled
from carla_safety_agent.io import scenario_from_dict
from carla_safety_agent.scenario_archive import read_verified_scenario
from carla_safety_agent.sensor_capture import atomic_json
from carla_safety_agent.session import SessionJournal

ROOT = Path(__file__).resolve().parents[1]


def main():
    stopped = False
    def stop(signum, frame):
        nonlocal stopped
        stopped = True
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    deadline = time.monotonic()+10
    journal = SessionJournal(ROOT/'data')
    while journal.owned_pid() != os.getpid():
        if time.monotonic() > deadline:
            raise RuntimeError('No verified studio session owns this rule worker')
        time.sleep(.05)
    execution = os.environ['CSA_EXECUTION_ID']
    if journal.snapshot()['run_id'] != execution:
        raise RuntimeError('Rule execution identity mismatch')
    document, digest = read_verified_scenario(os.environ['SCENARIO'], os.environ['CSA_SCENARIO_SHA256'])
    spec = scenario_from_dict(document)
    runtime = Path(os.environ['CSA_EVALUATION_CONTROL_DIR'])
    destination = Path(os.environ['RESULTS'])
    try:
        result = CarlaAdapter(port=int(os.environ.get('CARLA_PORT','2000')), timeout_s=30).run(
            spec, Path(os.environ['CSA_DATASET_ROOT']), render=True,
            capture_runtime=runtime if os.environ.get('CSA_RULE_CAPTURE') == '1' else None,
            should_stop=lambda: stopped)
        report = result.to_dict()
        # No actor-distance observation exists when cancelled before frame one.
        if not math.isfinite(report['min_distance_m']):
            report['min_distance_m'] = None
    except RuleRunCancelled:
        report = {'scenario_id':spec.scenario_id, 'status':'stopped', 'elapsed_s':0}
    report.update(execution_id=execution, scenario_sha256=digest, scenario=document)
    atomic_json(destination, report)


if __name__ == '__main__':
    main()

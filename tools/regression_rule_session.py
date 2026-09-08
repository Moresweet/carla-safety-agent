"""Real session-owned rule execution and unified dataset identity regression."""
import json
import argparse
import subprocess
import sys
import time
import urllib.error
from pathlib import Path
from regression_scene_versions import ROOT, request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--stop',action='store_true')
    args = parser.parse_args()
    assert request('system/preflight')['ready']
    plan = request('scenario/compile', {'description':'Town04 前车急刹，自车5 m/s','max_duration_s':20 if args.stop else 1})
    options = {'action':'rule-run','route':plan['scenario_path'],
               'scenario_sha256':plan['scenario_sha256'],'unified_capture':True}
    response = request('e2e/start', options)
    assert response['job']['algorithm'] is None
    execution = request('session/status')['session']['run_id']
    try:
        request('e2e/start', options)
    except urllib.error.HTTPError as exc:
        assert 'already running' in exc.read().decode()
    else:
        raise AssertionError('Duplicate task accepted')
    deadline = time.monotonic()+180
    stop_sent = False
    while time.monotonic() < deadline:
        session = request('session/status')['session']
        assert session['run_id'] == execution
        if session['state'] not in ('preparing','running','stopping','recovering'):
            break
        if args.stop and not stop_sent:
            for path in (ROOT/'.runtime/generated-scenarios').glob('capture-*/manifest.json'):
                manifest = json.loads(path.read_text())
                if manifest.get('execution_id') == execution and manifest['frame_count'] >= 5:
                    try:
                        request('scenario/stop', {'run_id':'stale-regression-id'})
                    except urllib.error.HTTPError as exc:
                        assert exc.code == 400
                    else:
                        raise AssertionError('Stale rule stop accepted')
                    assert request('session/status')['session']['run_id'] == execution
                    request('scenario/stop', {'run_id':execution})
                    stop_sent = True
                    break
        time.sleep(1)
    assert session['state'] == ('stopped' if args.stop else 'completed'), session
    result = json.loads(Path(session['configuration']['results']).read_text())
    assert result['execution_id'] == execution
    assert result['scenario_sha256'] == plan['scenario_sha256']
    assert result['scenario'] == plan['scenario']
    if args.stop:
        assert stop_sent and result['status'] == 'stopped' and result['elapsed_s'] < 20
    datasets = []
    for path in (ROOT/'.runtime/generated-scenarios').glob('capture-*/manifest.json'):
        manifest = json.loads(path.read_text())
        if manifest.get('execution_id') == execution:
            datasets.append(path.parent)
    assert len(datasets) == 1, datasets
    subprocess.run([sys.executable,str(ROOT/'tools/validate_capture_dataset.py'),str(datasets[0])],check=True)
    import carla
    client = carla.Client('127.0.0.1',2000); client.set_timeout(10)
    world = client.get_world()
    assert not world.get_settings().synchronous_mode
    assert not list(world.get_actors().filter('sensor.*'))
    report = {'execution_id':execution,'dataset':str(datasets[0]),'duplicate_rejected':True,
              'scenario_sha256':plan['scenario_sha256'],'state':session['state']}
    destination = ROOT/'runs/validation'/f'rule-session-{execution}.json'
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(report,indent=2))
    print(json.dumps(report),flush=True)


if __name__ == '__main__': main()

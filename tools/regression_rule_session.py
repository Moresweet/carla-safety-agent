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
    parser.add_argument('--protect-delete',action='store_true')
    args = parser.parse_args()
    if args.protect_delete and not args.stop:
        parser.error('--protect-delete requires --stop')
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
                    catalog = request('catalog/objects?category=buildings&limit=2')
                    assert catalog['total'] > 0 and len(catalog['objects']) == 2
                    assert all(item['origin'] == 'existing' for item in catalog['objects'])
                    if args.protect_delete:
                        index=json.loads((path.parent/'index.json').read_text())['frames']
                        first=json.loads((path.parent/index[0]['path']/'frame.json').read_text())
                        ego_id=first['ego']['id']
                        try:
                            request('objects/delete',{'actor_id':ego_id})
                        except urllib.error.HTTPError as exc:
                            assert 'attached sensors' in exc.read().decode()
                        else:
                            raise AssertionError('Sensor parent deletion was accepted')
                        after=json.loads((path.parent/'index.json').read_text())['frames']
                        assert after[-1]['frame']>index[-1]['frame'], 'Capture did not advance during refused deletion'
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
    from carla_safety_agent.owned_resources import read_resources, resource_path
    from carla_safety_agent.traffic_manager_ownership import require_stopped_manager
    resources=read_resources(resource_path(ROOT/'data',execution),session)
    assert resources['state']=='recovered'
    assert resources['traffic_manager']['port']==8051
    require_stopped_manager(resources['traffic_manager'])
    result = json.loads(Path(session['configuration']['results']).read_text())
    assert result['execution_id'] == execution
    assert result['scenario_sha256'] == plan['scenario_sha256']
    assert result['scenario'] == plan['scenario']
    if args.stop:
        assert stop_sent and result['status'] == 'stopped' and result['elapsed_s'] < 20
        records = [json.loads(path.read_text()) for path in Path(result['editor_commands']).glob('*.json')]
        catalogs = [item for item in records if (item.get('command') or {}).get('action') == 'catalog_environment']
        assert catalogs and any(item['response']['ok'] for item in catalogs)
        assert all(item['execution_id'] == execution for item in records)
        assert all(item['observed_frame_before'] == item['observed_frame_after'] for item in records)
        if args.protect_delete:
            rejected=[item for item in records if (item.get('command') or {}).get('action')=='delete']
            assert len(rejected)==1 and rejected[0]['response']['ok'] is False
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

"""Real short rule scenario: archived identity, raw multimodal data and cleanup."""
import json
import subprocess
import sys
import urllib.request
import uuid

from regression_scene_versions import ROOT, request
from carla_safety_agent.scenario_archive import read_verified_scenario


def main():
    preflight = request('system/preflight')
    assert preflight['ready'], preflight
    import carla
    client = carla.Client('127.0.0.1', 2000)
    client.set_timeout(10)
    world = client.get_world()
    assert world.get_map().name.endswith('/Town04'), 'Regression must not switch maps'
    assert not world.get_settings().synchronous_mode
    assert not list(world.get_actors().filter('sensor.*')), 'Existing sensors must not be disturbed'
    root = ROOT/'.runtime/generated-scenarios'
    previous = set(root.glob('capture-*'))
    payload = {'description':'Town04 前车急刹，自车 5 m/s',
               'max_duration_s':1, 'unified_capture':True}
    req = urllib.request.Request('http://127.0.0.1:8765/scenario/run',
        data=json.dumps(payload).encode(), headers={'Content-Type':'application/json'})
    # A timeout is not permission to repeat the simulation request.
    with urllib.request.urlopen(req, timeout=120) as response:
        result = json.load(response)
    assert result['ok'], result
    created = set(root.glob('capture-*')) - previous
    assert len(created) == 1, f'Ambiguous capture directories: {created}'
    dataset = created.pop()
    manifest = json.loads((dataset/'manifest.json').read_text())
    reference = manifest['scenario']
    scenario, digest = read_verified_scenario(dataset/reference['path'], reference['sha256'])
    assert scenario == result['scenario']
    assert digest == result['scenario_sha256']
    assert manifest['scenario_id'] == scenario['scenario_id']
    assert manifest['status'] == 'saved' and not manifest['cleanup_errors']
    assert manifest['frame_count'] > 0
    subprocess.run([sys.executable, str(ROOT/'tools/validate_capture_dataset.py'), str(dataset)], check=True)
    world = client.get_world()
    assert world.get_map().name.endswith('/Town04')
    assert not world.get_settings().synchronous_mode
    assert not list(world.get_actors().filter('sensor.*'))
    report = {'dataset':str(dataset), 'scenario_sha256':digest,
              'frames':manifest['frame_count'], 'raw_data_validated':True,
              'asynchronous_after':True, 'remaining_sensors':0}
    destination = ROOT/'runs/validation'/('rule-capture-'+uuid.uuid4().hex+'.json')
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2))
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()

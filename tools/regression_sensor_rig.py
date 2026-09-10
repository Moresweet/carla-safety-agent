"""Real independent rule-driving capture lifecycle and dataset verification."""
import json
import argparse
import subprocess
import sys
import time
import urllib.error
import uuid
from carla_safety_agent.world_health import observe_idle
from regression_material_slots import ROOT, request


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=('stationary','manual','autopilot'),default='autopilot')
    args=parser.parse_args()
    assert request('/system/preflight')['ready']
    result = request('/e2e/start', {'action':'sensor-rig','mode':args.mode,'frames':120,'every':3})
    assert result['job']['algorithm'] is None
    execution_id=request('/session/status')['session']['run_id']
    try:
        try:
            request('/e2e/start', {'action':'sensor-rig'})
        except urllib.error.HTTPError as exc:
            assert 'already running' in exc.read().decode()
        else:
            raise AssertionError('Duplicate execution was accepted')
        deadline = time.monotonic()+180
        while time.monotonic() < deadline:
            status = request('/session/status')['session']
            assert status['run_id']==execution_id, 'Execution changed during regression'
            if status['state'] in ('completed','stopped','failed'): break
            time.sleep(1)
        else: raise TimeoutError('Sensor rig did not finish')
        assert status['state']=='completed', status
        report = json.loads((ROOT/'.runtime/evaluation-control/sensor-rig-status.json').read_text())
        assert not report['cleanup_errors'] and report['recorded_frames'] > 0
        dataset = ROOT/'.runtime/generated-scenarios'/report['run_id']
        manifest=json.loads((dataset/'manifest.json').read_text())
        assert manifest['sampling_every_frames']==3
        assert manifest['execution_id']==execution_id, 'Dataset must link to its owning execution'
        from carla_safety_agent.data_quality import temporal_quality
        quality=temporal_quality(json.loads((dataset/'index.json').read_text())['frames'],3)
        assert quality['temporal_order_valid'] and not quality['unexpected_intervals'],quality
        subprocess.run([sys.executable,str(ROOT/'tools/validate_capture_dataset.py'),str(dataset)],check=True)
        frames = json.loads((dataset/'index.json').read_text())['frames']
        first,last = [json.loads((dataset/e['path']/'frame.json').read_text()) for e in (frames[0],frames[-1])]
        displacement = sum((last['ego']['matrix'][axis][3]-first['ego']['matrix'][axis][3])**2 for axis in range(3))**.5
        if args.mode=='autopilot':
            assert displacement > .5, 'Rule-driving vehicle did not move'
        from carla_safety_agent.owned_resources import read_resources,resource_path
        resources=read_resources(resource_path(ROOT/'data',execution_id),status)
        assert resources['state']=='recovered'
        if args.mode=='autopilot':
            from carla_safety_agent.traffic_manager_ownership import require_stopped_manager
            require_stopped_manager(resources['traffic_manager'])
        import carla
        client=carla.Client('127.0.0.1',2000); client.set_timeout(5)
        world=client.get_world()
        assert not world.get_settings().synchronous_mode
        assert not list(world.get_actors().filter('sensor.*'))
        assert not [a for a in world.get_actors().filter('vehicle.*') if a.attributes.get('role_name')=='sensor_rig']
        report.update(displacement_m=displacement,duplicate_start_rejected=True,dataset_validated=True,
                      temporal_quality=quality,post_exit_health=observe_idle(client,world.get_map().name))
        output=ROOT/'runs/validation'/('sensor-rig-'+uuid.uuid4().hex+'.json')
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(report,indent=2))
        print(json.dumps(report),flush=True)
        print(output,flush=True)
    finally:
        current=request('/session/status')['session']
        if current['run_id']==execution_id and current['state'] in ('preparing','running','stopping'):
            request('/collection/stop',{'run_id':execution_id})


if __name__ == '__main__': main()

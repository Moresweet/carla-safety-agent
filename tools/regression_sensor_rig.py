"""Real independent rule-driving capture lifecycle and dataset verification."""
import json
import subprocess
import sys
import time
import urllib.error
from regression_material_slots import ROOT, request


def main():
    assert request('/system/preflight')['ready']
    result = request('/e2e/start', {'action':'sensor-rig','mode':'autopilot','frames':120,'every':3})
    assert result['job']['algorithm'] is None
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
            if status['state'] in ('completed','stopped','failed'): break
            time.sleep(1)
        else: raise TimeoutError('Sensor rig did not finish')
        assert status['state']=='completed', status
        report = json.loads((ROOT/'.runtime/evaluation-control/sensor-rig-status.json').read_text())
        assert not report['cleanup_errors'] and report['recorded_frames'] > 0
        dataset = ROOT/'.runtime/generated-scenarios'/report['run_id']
        subprocess.run([sys.executable,str(ROOT/'tools/validate_capture_dataset.py'),str(dataset)],check=True)
        frames = json.loads((dataset/'index.json').read_text())['frames']
        first,last = [json.loads((dataset/e['path']/'frame.json').read_text()) for e in (frames[0],frames[-1])]
        displacement = sum((last['ego']['matrix'][axis][3]-first['ego']['matrix'][axis][3])**2 for axis in range(3))**.5
        assert displacement > .5, 'Rule-driving vehicle did not move'
        import carla
        client=carla.Client('127.0.0.1',2000); client.set_timeout(5)
        world=client.get_world()
        assert not world.get_settings().synchronous_mode
        assert not list(world.get_actors().filter('sensor.*'))
        assert not [a for a in world.get_actors().filter('vehicle.*') if a.attributes.get('role_name')=='sensor_rig']
        report.update(displacement_m=displacement,duplicate_start_rejected=True,dataset_validated=True)
        output=ROOT/'runs/validation/sensor-rig-20260908.json'
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(report,indent=2))
        print(json.dumps(report),flush=True)
    finally:
        state=request('/session/status')['session']['state']
        if state in ('preparing','running','stopping'):
            request('/e2e/stop',{})


if __name__ == '__main__': main()

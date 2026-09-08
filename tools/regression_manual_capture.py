"""Opt-in native manual control, watchdog brake, recording and cleanup regression."""
import json
import time
from regression_material_slots import ROOT,request


def main():
    assert request('/system/preflight')['ready']
    request('/collection/start',{'mode':'manual','frames':120,'every':1})
    execution=request('/session/status')['session']['run_id']
    try:
        deadline=time.monotonic()+45
        report_path=ROOT/'.runtime/evaluation-control/sensor-rig-status.json'
        while time.monotonic()<deadline:
            if report_path.exists() and json.loads(report_path.read_text()).get('frames',0)>=3: break
            time.sleep(.1)
        else: raise TimeoutError('Manual capture did not become ready')
        until=time.monotonic()+3
        while time.monotonic()<until:
            request('/collection/control',{'run_id':execution,'control':{'throttle':.35}})
            time.sleep(.1)
        # Deliberately stop sending commands; the worker must apply the watchdog brake.
        deadline=time.monotonic()+120
        while time.monotonic()<deadline:
            state=request('/session/status')['session']
            assert state['run_id']==execution
            if state['state'] in ('completed','stopped','failed'): break
            time.sleep(.5)
        else: raise TimeoutError('Manual capture did not finish')
        assert state['state']=='completed',state
        report=json.loads(report_path.read_text())
        dataset=ROOT/'.runtime/generated-scenarios'/report['run_id']
        entries=json.loads((dataset/'index.json').read_text())['frames']
        samples=[json.loads((dataset/e['path']/'frame.json').read_text()) for e in entries]
        assert any(s['control']['throttle']>.3 for s in samples), 'Manual throttle never applied'
        assert samples[-1]['control']['brake']==1 and samples[-1]['control']['throttle']==0
        first,last=samples[0]['ego']['matrix'],samples[-1]['ego']['matrix']
        distance=sum((last[a][3]-first[a][3])**2 for a in range(3))**.5
        assert distance>.05, 'Manual vehicle did not move'
        import carla
        client=carla.Client('127.0.0.1',2000);client.set_timeout(5)
        world=client.get_world()
        assert not world.get_settings().synchronous_mode
        assert not list(world.get_actors().filter('sensor.*'))
        assert not [a for a in world.get_actors().filter('vehicle.*') if a.attributes.get('role_name')=='sensor_rig']
        report.update(execution_id=execution,manual_throttle_observed=True,watchdog_brake_observed=True,distance_m=distance)
        output=ROOT/'runs/validation/manual-capture.json';output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
    finally:
        current=request('/session/status')['session']
        if current['run_id']==execution and current['state'] in ('preparing','running','stopping'):
            request('/collection/stop',{'run_id':execution})


if __name__=='__main__': main()

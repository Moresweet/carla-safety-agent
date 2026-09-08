"""Native limit termination must preserve committed samples and not fail the job."""
import json
import time
from regression_material_slots import ROOT,request


def main():
    assert request('/system/preflight')['ready']
    request('/collection/start',{'mode':'stationary','frames':100,'every':1,'max_frames':3})
    execution=request('/session/status')['session']['run_id']
    try:
        deadline=time.monotonic()+90
        while time.monotonic()<deadline:
            session=request('/session/status')['session']
            assert session['run_id']==execution
            if session['state'] in ('completed','stopped','failed'): break
            time.sleep(.5)
        else: raise TimeoutError('Limit capture did not finish')
        assert session['state']=='completed',session
        report=json.loads((ROOT/'.runtime/evaluation-control/sensor-rig-status.json').read_text())
        assert report['stop_reason']=='frame_limit' and not report['cleanup_errors'],report
        dataset=ROOT/'.runtime/generated-scenarios'/report['run_id']
        manifest=json.loads((dataset/'manifest.json').read_text())
        entries=json.loads((dataset/'index.json').read_text())['frames']
        assert manifest['status']=='saved_limit' and manifest['stop_reason']=='frame_limit'
        assert manifest['frame_count']==len(entries)==3
        assert manifest['execution_id']==execution
        import carla
        client=carla.Client('127.0.0.1',2000);client.set_timeout(5)
        world=client.get_world()
        assert not world.get_settings().synchronous_mode
        assert not list(world.get_actors().filter('sensor.*'))
        assert not [a for a in world.get_actors().filter('vehicle.*') if a.attributes.get('role_name')=='sensor_rig']
        print(json.dumps({'execution_id':execution,'dataset':report['run_id'],'samples':3,'state':session['state'],'stop_reason':manifest['stop_reason']}),flush=True)
    finally:
        current=request('/session/status')['session']
        if current['run_id']==execution and current['state'] in ('preparing','running','stopping'):
            request('/collection/stop',{'run_id':execution})


if __name__=='__main__': main()

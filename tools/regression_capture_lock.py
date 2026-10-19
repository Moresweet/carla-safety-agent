"""Real session-owned stationary capture under a controlled write-lock conflict."""
import json
import time
import uuid
from carla_safety_agent.capture_quota import capture_write_lock
from cleanup_superseded_model_captures import idle
from regression_material_slots import ROOT, request


def main():
    idle()
    assert request('/system/preflight')['ready']
    output=ROOT/'runs/validation'/('capture-lock-'+uuid.uuid4().hex+'.json')
    report={'passed':False,'scope':'Controlled advisory write-lock conflict, not disk exhaustion or CARLA crash'}
    execution=None
    try:
        with capture_write_lock(ROOT/'.runtime/generated-scenarios'):
            started=request('/e2e/start',{'action':'sensor-rig','mode':'stationary','frames':10,'every':1})
            execution=request('/session/status')['session']['run_id']
            report.update(execution_id=execution,started=started)
            deadline=time.monotonic()+90
            while time.monotonic()<deadline:
                session=request('/session/status')['session']
                assert session['run_id']==execution,'Session ownership changed'
                if session['state'] in ('completed','stopped','failed'):break
                time.sleep(.5)
            else:raise TimeoutError('Capture lock conflict did not terminate')
            report['session']=session
            assert session['state']=='failed',session
            assert session['outcome']['failure_category']=='capture_io_error',session
            assert 'Another capture writer holds admission lock' in session['error']
        status=json.loads((ROOT/'.runtime/evaluation-control/sensor-rig-status.json').read_text())
        report['worker']=status
        assert status['execution_id']==execution
        assert 'Another capture writer holds admission lock' in status['error']
        assert status['stop_reason']=='capture_io_error'
        assert status['recorded_frames']==0 and status['cleanup_errors']==[]
        folder=ROOT/'.runtime/generated-scenarios'/status['run_id']
        manifest=json.loads((folder/'manifest.json').read_text())
        report['manifest']=manifest
        assert manifest['execution_id']==execution
        assert manifest['status']=='saved_capture_error' and manifest['frame_count']==0
        assert json.loads((folder/'index.json').read_text())['frames']==[]
        import carla
        client=carla.Client('127.0.0.1',2000);client.set_timeout(5)
        world=client.get_world()
        report['remaining_sensors']=[a.id for a in world.get_actors().filter('sensor.*')]
        report['remaining_capture_vehicles']=[a.id for a in world.get_actors().filter('vehicle.*') if a.attributes.get('role_name')=='sensor_rig']
        assert not report['remaining_sensors'] and not report['remaining_capture_vehicles']
        assert not world.get_settings().synchronous_mode
        idle();assert request('/system/preflight')['ready']
        report['passed']=True
    except Exception as error:
        report['error']=str(error)
        raise
    finally:
        try:
            if execution:
                current=request('/session/status')['session']
                if current['run_id']==execution and current['state'] in ('preparing','running','stopping'):
                    report['stop_requested']=request('/collection/stop',{'run_id':execution})
                    report['passed']=False
        finally:
            output.write_text(json.dumps(report,indent=2))
            print(json.dumps({'receipt':str(output),'passed':report['passed']}),flush=True)


if __name__=='__main__':main()

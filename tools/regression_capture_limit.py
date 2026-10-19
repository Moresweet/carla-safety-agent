"""Native limit termination must preserve committed samples and not fail the job."""
import json
import time
import argparse
import uuid
import sys
from carla_safety_agent.capture_quality import audit_capture
from regression_material_slots import ROOT,request


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--samples',type=int,choices=(2,3),default=3)
    parser.add_argument('--verify-preview-cache',action='store_true')
    args=parser.parse_args()
    samples=args.samples
    live=ROOT/'.runtime/evaluation-control/capture'
    previous_generations={path.name for path in (live/'frames').iterdir()} if (live/'frames').exists() else set()
    assert request('/system/preflight')['ready']
    request('/collection/start',{'mode':'stationary','frames':100,'every':1,'max_frames':samples})
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
        assert manifest['frame_count']==len(entries)==samples
        assert report['frames']<100 and report['execution_id']==execution
        assert manifest['execution_id']==execution
        quality=audit_capture(dataset,ROOT/'tools/validate_capture_dataset.py',sys.executable)
        assert quality['state']=='passed',quality
        journal=json.loads((ROOT/'data/experiments'/execution/'execution.json').read_text())
        scene=journal['configuration']['starting_scene']
        assert scene['map']==manifest['map']
        assert all(key in scene for key in ('objects','environment_materials','hidden_environment','weather','spectator','limitations'))
        import carla
        client=carla.Client('127.0.0.1',2000);client.set_timeout(5)
        world=client.get_world()
        assert not world.get_settings().synchronous_mode
        assert not list(world.get_actors().filter('sensor.*'))
        assert not [a for a in world.get_actors().filter('vehicle.*') if a.attributes.get('role_name')=='sensor_rig']
        receipt={'execution_id':execution,'dataset':report['run_id'],'samples':samples,'state':session['state'],'stop_reason':manifest['stop_reason'],
                 'starting_scene_map':scene['map'],'managed_objects':len(scene['objects']),
                 'worker':report,'quality':quality,'asynchronous':True,'remaining_sensors':0,'remaining_capture_vehicles':0}
        if args.verify_preview_cache:
            preview=json.loads((live/'latest.json').read_text())
            assert 'preview_cleanup_error' in preview, 'New preview writer not loaded'
            assert preview['preview_cleanup_error'] is None, preview
            assert preview['run_id']==report['run_id'] and preview['frame']>=entries[-1]['frame'], preview
            assert (live/preview['generation']).is_dir()
            remaining={path.name for path in (live/'frames').iterdir()}
            assert len(remaining)<=12, remaining
            receipt['preview_cache']={'before':sorted(previous_generations),'after':sorted(remaining),
                'current':preview['generation'],'cleanup_error':None,
                'removed_old_generations':sorted(previous_generations-remaining)}
        output=ROOT/'runs/validation'/('capture-limit-'+uuid.uuid4().hex+'.json')
        output.write_text(json.dumps(receipt,indent=2))
        print(json.dumps({'receipt':str(output),**receipt}),flush=True)
    finally:
        current=request('/session/status')['session']
        if current['run_id']==execution and current['state'] in ('preparing','running','stopping'):
            request('/collection/stop',{'run_id':execution})


if __name__=='__main__': main()

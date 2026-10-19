"""Opt-in real zero-sample quota stop; requires a deliberately low bridge quota."""
import json
import time
import uuid
from pathlib import Path
from regression_material_slots import ROOT, request
from carla_safety_agent.world_health import observe_idle


def main():
    # Refuse accidental normal recording when the operator forgot the bounded
    # test configuration. Inspect only the relevant local process identity/key.
    pid = int((ROOT/'.runtime/bridge.pid').read_text())
    cwd = Path(f'/proc/{pid}/cwd').resolve(strict=True)
    argv = Path(f'/proc/{pid}/cmdline').read_bytes().decode().split('\0')
    environment = Path(f'/proc/{pid}/environ').read_bytes().decode().split('\0')
    from carla_safety_agent.capture_storage import inventory_captures
    from carla_safety_agent.restart_guard import verify_dataset_jobs_idle, verify_idle
    verify_dataset_jobs_idle(request('/datasets/jobs'))
    verify_idle(request('/session/status')['session'],request('/batches/scheduler')['scheduler'])
    usage = inventory_captures(ROOT/'.runtime/generated-scenarios')
    from carla_safety_agent.capture_quota import verify_quota_probe
    verify_quota_probe(ROOT,cwd,argv,environment,usage)
    import carla
    client = carla.Client('127.0.0.1',2000); client.set_timeout(10)
    world = client.get_world(); episode = world.id
    assert not world.get_settings().synchronous_mode
    request('/e2e/start', {'action':'sensor-rig','mode':'stationary','frames':30,'every':1})
    execution = request('/session/status')['session']['run_id']
    try:
        deadline = time.monotonic()+120
        while time.monotonic()<deadline:
            state = request('/session/status')['session']
            assert state['run_id']==execution
            if state['state'] in ('completed','failed','stopped'): break
            time.sleep(1)
        else: raise TimeoutError('Quota test still running; stop only its owned execution')
        assert state['state']=='completed', state
        report = json.loads((ROOT/'.runtime/evaluation-control/sensor-rig-status.json').read_text())
        assert report['stop_reason']=='capture_quota' and report['recorded_frames']==0, report
        assert report['cleanup_errors']==[], report
        dataset = ROOT/'.runtime/generated-scenarios'/report['run_id']
        manifest = json.loads((dataset/'manifest.json').read_text())
        assert manifest['execution_id']==execution
        assert manifest['status']=='saved_limit' and manifest['stop_reason']=='capture_quota'
        assert manifest['frame_count']==0
        assert manifest['capture_quota_policy']['limit_bytes']==90*1024**3
        assert json.loads((dataset/'index.json').read_text())['frames']==[]
        assert not (dataset/'samples').exists()
        health = observe_idle(client,world.get_map().name)
        assert health['episode']==episode and health['sensors']==0 and not health['synchronous']
        result = {'passed':True,'execution_id':execution,'run_id':report['run_id'],
            'manifest':manifest,'health':health,
            'scope':'Quota rejects first sample without filling disk; not mid-recording or concurrent-writer acceptance'}
        output = ROOT/'runs/validation'/('capture-quota-stop-'+uuid.uuid4().hex+'.json')
        with output.open('x') as stream: json.dump(result,stream,ensure_ascii=False,indent=2)
        print(json.dumps({'passed':True,'run_id':report['run_id'],'receipt':str(output)}))
    finally:
        current = request('/session/status')['session']
        if current['run_id']==execution and current['state'] in ('preparing','running','stopping'):
            request('/collection/stop',{'run_id':execution})


if __name__=='__main__': main()

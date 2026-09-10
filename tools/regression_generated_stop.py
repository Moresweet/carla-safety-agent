"""Native generated-model duplicate/stale-stop/owned-stop regression."""
import argparse
import json
import time
import uuid
import subprocess
from urllib.error import HTTPError
from regression_scene_versions import ROOT, request


def rejected(path,payload):
    try: request(path,payload)
    except HTTPError as exc:
        assert exc.code==400
        return json.load(exc)['error']
    raise AssertionError('Unsafe request accepted: '+path)


def verify_stopped(execution, phase):
    deadline=time.monotonic()+120
    while True:
        current=request('session/status')['session']
        assert current['run_id']==execution
        if current['state'] not in ('preparing','running','stopping','recovering'):break
        if time.monotonic()>deadline:raise RuntimeError('Stop still recovering; do not force-start another task')
        time.sleep(.5)
    assert current['state']=='stopped' and not current.get('error'),current
    if phase=='driving': assert current.get('returncode')==130, 'Expected explicit user-interruption exit code'
    assert 'Runtime cleanup incomplete' not in request('e2e/status')['log']
    import carla
    client=carla.Client('127.0.0.1',2000);client.set_timeout(10)
    world=client.get_world()
    assert not world.get_settings().synchronous_mode
    assert not list(world.get_actors().filter('sensor.*'))
    assert request('system/preflight')['ready']
    assert request('e2e/telemetry')['telemetry'] is None
    return current


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model',choices=['vad','tcp','admlp','uniad-tiny','uniad-base'],default='vad')
    parser.add_argument('--phase',choices=['immediate','driving'],default='driving')
    parser.add_argument('--browser-stop',action='store_true',help='Click the real UI Stop button through isolated Chrome with an exact-ID network guard')
    parser.add_argument('--verify-run',help='Only verify this existing execution after an interrupted test controller; never launch or signal')
    args=parser.parse_args()
    if args.verify_run:
        current=verify_stopped(args.verify_run,args.phase)
        output=ROOT/'runs/validation'/('stopped-verification-'+uuid.uuid4().hex+'.json')
        result={'execution_id':args.verify_run,'state':'verified','returncode':current.get('returncode'),
                'async_and_no_sensors':True,'launch_or_signal_sent':False}
        output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,indent=2))
        print(json.dumps({'report':str(output),**result}),flush=True);return
    assert request('system/preflight')['ready']
    assert request('e2e/status').get('stop_requires_run_id') is True, 'Reload the identity-scoped stop API before this regression'
    assert request('batches/scheduler')['scheduler']['state']!='running'
    plan=request('scenario/compile',{'description':'Town04 前车急刹，自车 5 m/s','max_duration_s':30})
    payload={'action':'run','algorithm':args.model,'route':plan['scenario_path'],
        'scenario_sha256':plan['scenario_sha256'],'unified_capture':True}
    started=request('e2e/start',payload)
    execution=started['execution_id']
    output=ROOT/'runs/validation'/('generated-stop-'+uuid.uuid4().hex+'.json')
    output.parent.mkdir(parents=True,exist_ok=True)
    result={'model':args.model,'phase':args.phase,'execution_id':execution,'state':'started'}
    output.write_text(json.dumps(result))
    print(json.dumps(result),flush=True)
    result['duplicate_error']=rejected('e2e/start',payload)
    result['stale_stop_error']=rejected('e2e/stop',{'run_id':uuid.uuid4().hex})
    assert request('session/status')['session']['run_id']==execution
    if args.phase=='driving':
        deadline=time.monotonic()+300
        while True:
            current=request('session/status')['session']
            assert current['run_id']==execution and current['state']=='running', current
            telemetry=request('e2e/telemetry').get('telemetry')
            if telemetry and telemetry.get('elapsed_s',0)>=.2:
                result['observed_frame']=telemetry['frame'];break
            if time.monotonic()>deadline: raise RuntimeError('No driving frame; execution remains owned for inspection')
            time.sleep(.25)
    if args.browser_stop:
        subprocess.run(['/home/moresweet/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node',
            str(ROOT/'tools/browser_reviewed_models.mjs'),'--stop-run',execution],cwd=ROOT,check=True)
        result['stop_source']='actual_browser_button'
    else:
        assert request('e2e/stop',{'run_id':execution})['run_id']==execution
        result['stop_source']='http_endpoint'
    current=verify_stopped(execution,args.phase)
    result.update(state='verified',returncode=current.get('returncode'),async_and_no_sensors=True,
        scope='Explicit owned stop; not forced process kill or native server crash')
    output.write_text(json.dumps(result,indent=2));print(json.dumps({'report':str(output),**result}),flush=True)


if __name__=='__main__':main()

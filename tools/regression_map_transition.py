"""Explicit real-model Town04 -> Town05 -> Town04 regression on an empty editor."""
import argparse
import json
import subprocess
import sys
import time
import uuid
import shutil

from regression_scene_versions import ROOT, request
from carla_safety_agent.world_health import observe_idle
from carla_safety_agent.world_readiness import map_matches, require_idle_native_world


def main():
    if not __debug__:
        raise RuntimeError('Acceptance requires assertions; do not use Python -O')
    import carla
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', choices=['vad','tcp','admlp','uniad-tiny','uniad-base','thinktwice','driveadapter'], required=True)
    args = parser.parse_args()
    original = args.model in ('thinktwice','driveadapter')
    duration = 4 if original else 1
    # Both recordings must fit before the first map transition, including
    # headroom; do not strand the editor on Town05 due to predictable capacity.
    storage = None
    if original:
        from carla_safety_agent.acceptance_storage import require_original_capture_space
        storage = require_original_capture_space(ROOT, capture_count=2, disk_usage=shutil.disk_usage)
    assert request('system/preflight')['ready']
    assert request('batches/scheduler')['scheduler']['state'] != 'running'
    client = carla.Client('127.0.0.1',2000)
    client.set_timeout(15)
    world = client.get_world()
    require_idle_native_world(world)
    assert map_matches('Town04',world.get_map().name), 'Test must begin on Town04'
    assert any(map_matches('Town05',name) for name in client.get_available_maps())
    for kind in ('vehicle.*','walker.*'):
        assert not list(world.get_actors().filter(kind)), 'Do not discard unrelated dynamic actors'
    saved = request('scenes/save',{'name':'切图回归前工作台快照'})
    document = saved['document']
    assert not document['objects'] and not document.get('environment_materials') and not document.get('hidden_environment'), 'Test requires an empty, unmodified editor'
    report = {'model':args.model,'saved_scene':saved['head']['scene_id'],'runs':[],
              'storage_admission':storage,
              'duration_s_per_map':duration,
              'scope':'Two real model runs across Town05 and Town04; not arbitrary map/crash coverage'}
    output = ROOT/'runs/validation'/('map-transition-'+uuid.uuid4().hex+'.json')
    output.parent.mkdir(parents=True,exist_ok=True)
    def save(): output.write_text(json.dumps(report,indent=2))
    save()
    for town in ('Town05','Town04'):
        before = client.get_world().id
        plan = request('scenario/compile',{'description':f'{town} 前车急刹，自车 5 m/s','max_duration_s':duration})
        response = request('scenario/execute-plan',{'confirmed':True,'scenario_path':plan['scenario_path'],
            'scenario_sha256':plan['scenario_sha256'],'algorithm':args.model,'unified_capture':True})
        run = {'map':town,'execution_id':response['execution_id'],'state':'started','episode_before':before}
        report['runs'].append(run);save()
        print(json.dumps(run),flush=True)
        deadline = time.monotonic()+600
        while True:
            try:
                session = request('session/status')['session']
            except Exception as error:
                run.update(state='controller_error',error=str(error));save()
                raise
            assert session['run_id']==run['execution_id'], 'Execution ownership changed'
            if session['state']=='recovering' and session.get('error'):
                run.update(state='needs_recovery',error=session['error'],returncode=session.get('returncode'));save()
                raise RuntimeError('Native recovery required; no further map transition attempted')
            if session['state'] not in ('preparing','running','stopping','recovering'):break
            if time.monotonic()>deadline:raise RuntimeError('Execution remains active; inspect without starting another task')
            time.sleep(1)
        run['session_state'],run['returncode'] = session['state'],session.get('returncode');save()
        if session['state']!='completed' or session['returncode']!=0:
            run.update(state='failed',error=session.get('error'));save()
            raise RuntimeError(f'Execution failed: {session}')
        world = client.get_world()
        require_idle_native_world(world)
        assert map_matches(town,world.get_map().name) and world.id != before
        run['post_exit_health'] = observe_idle(client,town)
        run['episode_after'] = world.id
        datasets = []
        for path in (ROOT/'.runtime/generated-scenarios').glob('capture-*/manifest.json'):
            manifest = json.loads(path.read_text())
            if manifest.get('execution_id') == run['execution_id']:
                subprocess.run([sys.executable,str(ROOT/'tools/validate_capture_dataset.py'),str(path.parent)],check=True)
                if original:
                    assert manifest['frame_count'] == 80 and manifest['status'] == 'saved', manifest
                    assert not manifest.get('error') and not manifest.get('stop_reason'), manifest
                    subprocess.run([sys.executable,str(ROOT/'tools/validate_thinktwice_prediction.py'),
                                    str(path.parent),'--model',args.model],check=True)
                datasets.append(str(path.parent))
        assert datasets, 'No unified capture was saved'
        assert request('system/preflight')['ready']
        run.update(state='verified',datasets=datasets);save()
        print(json.dumps(run),flush=True)
    request('scenes/restore',{'scene_id':saved['head']['scene_id']})
    report['original_editor_restored']=True;save()
    print(output,flush=True)


if __name__ == '__main__':main()

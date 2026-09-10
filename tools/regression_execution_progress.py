"""Opt-in real model stage/countdown/browser verification, not simulated progress."""
import argparse
import json
import subprocess
import sys
import time
import uuid
from pathlib import Path
from regression_scene_versions import ROOT,request
from carla_safety_agent.scene_store import atomic
from carla_safety_agent.world_health import observe_idle


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model',choices=['vad','tcp','admlp','uniad-tiny','uniad-base'],required=True)
    parser.add_argument('--node',type=Path,required=True)
    args=parser.parse_args()
    assert request('system/preflight')['ready']
    assert request('batches/scheduler')['scheduler']['state']!='running'
    plan=request('scenario/compile',{'description':'Town04 前车急刹，自车 5 m/s','max_duration_s':1})
    response=request('scenario/execute-plan',{'confirmed':True,'scenario_path':plan['scenario_path'],
        'scenario_sha256':plan['scenario_sha256'],'algorithm':args.model,'unified_capture':True})
    execution=response['execution_id'];output=ROOT/'runs/validation'/('execution-progress-'+uuid.uuid4().hex+'.json')
    report={'execution_id':execution,'model':args.model,'state':'observing','phases':[],
        'scope':'Real short native model run; advisory stages do not certify driver safety or detect every hang'}
    atomic(output,report);print(output,flush=True)
    try:
        deadline=time.monotonic()+600;browser_checked=False
        while time.monotonic()<deadline:
            status=request('session/status');session=status['session'];progress=status['progress']
            assert session['run_id']==execution,'Execution ownership changed'
            if progress.get('available'):
                assert progress['run_id']==execution and progress['owner']==session['process']
                if not report['phases'] or report['phases'][-1]['phase']!=progress['phase']:
                    report['phases'].append(progress);atomic(output,report)
                    print(json.dumps({'phase':progress['phase'],'state':session['state']}),flush=True)
                if progress['phase']=='preview' and not browser_checked:
                    assert progress['completed_steps']>0 and progress['preview_remaining_s']>20
                    screenshot=subprocess.run([str(args.node),str(ROOT/'tools/browser_reviewed_models.mjs'),
                        '--expect-execution-phase','preview',execution],cwd=ROOT,capture_output=True,text=True,timeout=45)
                    report['browser_stdout']=screenshot.stdout;report['browser_stderr']=screenshot.stderr
                    assert screenshot.returncode==0,screenshot.stderr
                    next_status=request('session/status')
                    assert next_status['session']['run_id']==execution
                    next_progress=next_status['progress']
                    assert next_progress['preview_remaining_s']<progress['preview_remaining_s']
                    report['preview_countdown_decreased']=True;browser_checked=True;atomic(output,report)
            if session['state'] not in ('preparing','running','stopping','recovering'):break
            time.sleep(.25)
        else:raise TimeoutError('Owned execution remains active')
        assert session['state']=='completed' and session['returncode']==0,session
        assert browser_checked
        phases={row['phase'] for row in report['phases']}
        assert {'loading_model','inference','preview','worker_finished'}<=phases,phases
        captures=[]
        for path in (ROOT/'.runtime/generated-scenarios').glob('capture-*/manifest.json'):
            if json.loads(path.read_text()).get('execution_id')==execution:
                subprocess.run([sys.executable,str(ROOT/'tools/validate_capture_dataset.py'),str(path.parent)],check=True)
                captures.append(str(path.parent))
        assert captures
        import carla
        client=carla.Client('127.0.0.1',2000);client.set_timeout(10)
        report.update(state='verified',captures=captures,health=observe_idle(client,'Town04'))
    except Exception as exc:
        report.update(state='failed',error=str(exc));raise
    finally:
        atomic(output,report)
        current=request('session/status')['session']
        if current['run_id']==execution and current['state'] in ('preparing','running','stopping'):
            request('e2e/stop',{'run_id':execution})
    print(output,flush=True)


if __name__=='__main__':main()

"""Explicit browser plan fork followed by exact-archive native rule execution."""
import argparse
import json
import subprocess
import sys
import time
import uuid
from pathlib import Path
import carla
from regression_scene_versions import ROOT,request
from carla_safety_agent.world_health import observe_idle


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--node',required=True)
    args=parser.parse_args();assert request('system/preflight')['ready']
    client=carla.Client('127.0.0.1',2000);client.set_timeout(10);world=client.get_world()
    episode=world.id;camera=world.get_spectator().get_transform();actors={a.id for a in world.get_actors()}
    proc=subprocess.run([args.node,str(ROOT/'tools/browser_reviewed_models.mjs'),'--plan-revision'],cwd=ROOT,text=True,capture_output=True,timeout=180)
    if proc.returncode:raise RuntimeError(proc.stdout+'\n'+proc.stderr)
    browser=json.loads(proc.stdout.strip().splitlines()[-1]);print(json.dumps(browser),flush=True)
    plans=json.loads((Path(browser['output'])/'plan-revision-result.json').read_text());child=plans['child']
    assert client.get_world().id==episode and {a.id for a in world.get_actors()}==actors,'Plan editing changed native world'
    request('e2e/start',{'action':'rule-run','route':child['scenario_path'],'scenario_sha256':child['scenario_sha256'],'unified_capture':True})
    execution=request('session/status')['session']['run_id'];deadline=time.monotonic()+120
    while time.monotonic()<deadline:
        session=request('session/status')['session'];assert session['run_id']==execution
        if session['state'] not in ('preparing','running','stopping','recovering'):break
        time.sleep(.5)
    assert session['state']=='completed' and session['returncode']==0,session
    assert session['configuration']['request']['scenario_sha256']==child['scenario_sha256']
    result=json.loads(Path(session['configuration']['results']).read_text())
    assert result['scenario']['ego']['speed_mps']==5 and result['scenario']['environment']['precipitation']==0
    captures=[]
    for path in (ROOT/'.runtime/generated-scenarios').glob('capture-*/manifest.json'):
        if json.loads(path.read_text()).get('execution_id')==execution:
            subprocess.run([sys.executable,str(ROOT/'tools/validate_capture_dataset.py'),str(path.parent)],check=True)
            captures.append(str(path.parent))
    assert len(captures)==1
    health=observe_idle(client,world.get_map().name,seconds=5.)
    world=client.get_world();world.get_spectator().set_transform(camera)
    assert world.id==episode
    assert {a.id for a in world.get_actors()}==actors
    report={'passed':True,'execution_id':execution,'parent_sha256':plans['parent']['scenario_sha256'],
        'child_sha256':child['scenario_sha256'],'browser':browser,'captures':captures,'health':health,
        'scope':'Bounded field edits, explicit adoption and exact revised archive execution; not arbitrary language or Blender generation'}
    output=ROOT/'runs/validation'/('plan-revision-'+uuid.uuid4().hex+'.json');output.write_text(json.dumps(report,indent=2));print(json.dumps({'report':str(output),'passed':True}),flush=True)


if __name__=='__main__':main()

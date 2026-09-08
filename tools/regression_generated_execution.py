"""Run a short real UniAD scenario and verify archived configuration identity."""
import hashlib
import json
import time
from pathlib import Path
from regression_scene_versions import request


def main():
    assert request('system/preflight')['ready']
    plan=request('scenario/compile', {'description':'Town04 前车急刹，自车 5 m/s', 'max_duration_s':1})
    digest=plan['scenario_sha256']
    assert hashlib.sha256(Path(plan['scenario_path']).read_bytes()).hexdigest()==digest
    request('e2e/start',{'action':'run','algorithm':'uniad-tiny','route':plan['scenario_path']})
    session=request('session/status')['session']
    execution=session['run_id']
    try:
        assert session['configuration']['scenario_sha256']==digest
        deadline=time.monotonic()+300
        while time.monotonic()<deadline:
            session=request('session/status')['session']
            assert session['run_id']==execution
            if session['state'] not in ('preparing','running','stopping','recovering'):
                break
            if session.get('error'): raise RuntimeError(session['error'])
            time.sleep(1)
        assert session['state']=='completed', session
        result=json.loads(Path(session['configuration']['results']).read_text())
        assert result['scenario_sha256']==digest
        assert result['trace'], 'Model produced no driving frames'
        assert result['scenario']==plan['scenario']
        preflight=request('system/preflight')
        assert preflight['ready']
        assert next(c for c in preflight['checks'] if c['id']=='carla')['synchronous'] is False
        print(json.dumps({'execution_id':execution,'scenario_sha256':digest,
                          'frames':len(result['trace']),'state':session['state']}),flush=True)
    finally:
        current=request('session/status')['session']
        if current['run_id']==execution and current['state'] in ('preparing','running','stopping'):
            request('e2e/stop',{})


if __name__=='__main__': main()

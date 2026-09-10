"""Run a short real UniAD scenario and verify archived configuration identity."""
import hashlib
import json
import time
import urllib.error
from pathlib import Path
from regression_scene_versions import request


def main():
    assert request('system/preflight')['ready']
    plan=request('scenario/compile', {'description':'Town04 前车急刹，自车 5 m/s', 'max_duration_s':1})
    digest=plan['scenario_sha256']
    previous={p:hashlib.sha256(p.read_bytes()).hexdigest()
              for p in (Path(__file__).resolve().parents[1]/'runs/uniad').glob(Path(plan['scenario_path']).stem+'*.json')}
    assert hashlib.sha256(Path(plan['scenario_path']).read_bytes()).hexdigest()==digest
    before=request('session/status')['session']['run_id']
    try:
        request('scenario/execute-plan',{'confirmed':True,'scenario_path':plan['scenario_path'],
                                         'scenario_sha256':'0'*64})
    except urllib.error.HTTPError as exc:
        assert exc.code==400
        assert 'changed' in json.load(exc)['error']
    else:
        raise AssertionError('Mismatched reviewed plan was accepted')
    assert request('session/status')['session']['run_id']==before
    request('scenario/execute-plan',{'confirmed':True,'scenario_path':plan['scenario_path'],
                                     'scenario_sha256':digest})
    session=request('session/status')['session']
    execution=session['run_id']
    try:
        assert session['configuration']['scenario_sha256']==digest
        assert session['configuration']['request']['confirmed'] is True
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
        assert result['execution_id']==execution
        assert Path(session['configuration']['results']) not in previous
        assert all(hashlib.sha256(p.read_bytes()).hexdigest()==value for p,value in previous.items())
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
            request('e2e/stop',{'run_id':execution})


if __name__=='__main__': main()

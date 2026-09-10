"""Opt-in native reviewed-plan routing and capture-toggle regression."""
import argparse
import json
import subprocess
import sys
import time
import uuid
from regression_scene_versions import ROOT, request


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--models', nargs='+', choices=['uniad-tiny','uniad-base','vad','tcp','admlp'], required=True)
    parser.add_argument('--capture', action='store_true')
    parser.add_argument('--description', default='Town04 前车急刹，自车 5 m/s')
    parser.add_argument('--require-generated-assets', action='store_true')
    parser.add_argument('--require-prediction-contract',action='store_true')
    args=parser.parse_args()
    if args.require_prediction_contract and not args.capture:
        parser.error('--require-prediction-contract requires --capture')
    assert request('system/preflight')['ready']
    assert request('batches/scheduler')['scheduler']['state']!='running'
    rows=[]
    output=ROOT/'runs/validation'/('reviewed-models-'+uuid.uuid4().hex+'.json')
    for model in args.models:
        duration=3 if args.require_prediction_contract and model=='admlp' else 1
        prediction_counts={'warmup':0,'fresh':0,'reused':0}
        plan=request('scenario/compile',{'description':args.description,'max_duration_s':duration})
        if args.require_generated_assets:
            from pathlib import Path
            document=json.loads(Path(plan['scenario_path']).read_text())
            assert document.get('generated_assets'), 'Requested generated-asset fixture was not compiled'
        response=request('scenario/execute-plan',{'confirmed':True,'scenario_path':plan['scenario_path'],
            'scenario_sha256':plan['scenario_sha256'],'algorithm':model,'unified_capture':args.capture})
        execution=response['execution_id']
        print(json.dumps({'model':model,'execution_id':execution,'state':'started'}),flush=True)
        deadline=time.monotonic()+600
        while True:
            session=request('session/status')['session']
            assert session['run_id']==execution, 'Ownership changed; do not mutate another execution'
            if session['state'] not in ('preparing','running','stopping','recovering'): break
            if time.monotonic()>deadline: raise RuntimeError('Execution still active; retain ownership and inspect session')
            time.sleep(1)
        assert session['state']=='completed' and session['returncode']==0, session
        actual=session['configuration']['request']
        assert actual['algorithm']==model and actual['unified_capture']==args.capture
        assert actual['scenario_sha256']==plan['scenario_sha256']
        captures=[]
        for path in (ROOT/'.runtime/generated-scenarios').glob('capture-*/manifest.json'):
            if json.loads(path.read_text()).get('execution_id')==execution: captures.append(path.parent)
        assert bool(captures)==args.capture, 'Capture toggle not honored'
        for dataset in captures:
            subprocess.run([sys.executable,str(ROOT/'tools/validate_capture_dataset.py'),str(dataset)],check=True)
            if args.require_prediction_contract:
                from carla_safety_agent.prediction_trajectory import replay_prediction
                entries=json.loads((dataset/'index.json').read_text())['frames']
                assert entries
                for entry in entries:
                    metadata=json.loads((dataset/entry['path']/'frame.json').read_text())
                    prediction=replay_prediction(metadata,metadata['ego']['matrix'])
                    if prediction.get('source_state')=='warmup':
                        assert model in ('tcp','admlp')
                        warmup=metadata['prediction']
                        assert 0<=metadata['model_step']<warmup['required_history_steps']
                        assert metadata['planning_observed_calls']==0 and metadata['planning_anchor'] is None
                        prediction_counts['warmup']+=1
                        continue
                    assert prediction['state']=='available',prediction
                    assert prediction['points'] and prediction['timing_verified'] is False
                    prediction_counts['reused' if prediction['reused'] else 'fresh']+=1
                assert prediction_counts['fresh']>0,'Only warm-up was exercised; no real planning output'
                if model=='admlp':
                    assert prediction_counts['fresh']>=2 and prediction_counts['reused']>0
        import carla
        client=carla.Client('127.0.0.1',2000);client.set_timeout(10)
        world=client.get_world()
        assert not world.get_settings().synchronous_mode
        assert not list(world.get_actors().filter('sensor.*'))
        if args.require_generated_assets:
            from carla_safety_agent.owned_resources import read_resources,resource_path
            resources=read_resources(resource_path(ROOT/'data',execution),session)
            assert resources['state']=='recovered'
            assert sum(row['type_id']=='static.prop.mesh' for row in resources['actors']) == sum(asset['count'] for asset in document['generated_assets'])
        rows.append({'model':model,'execution_id':execution,'capture_requested':args.capture,
                     'prediction_spatial_contract_verified':args.require_prediction_contract,
                     'duration_s':duration,'prediction_frames':prediction_counts,
                     'captures':[str(p) for p in captures],'cleanup_verified':True})
        output.write_text(json.dumps({'scope':'Short native reviewed-plan routing, capture and cleanup; ADMLP prediction probe is 3s to exceed warm-up; not driving quality','runs':rows},indent=2))
        print(json.dumps({'model':model,'state':'verified','report':str(output)}),flush=True)


if __name__=='__main__':main()

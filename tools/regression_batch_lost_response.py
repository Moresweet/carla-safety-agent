"""Native batch binding recovery after an injected post-launch response failure.

The real launch succeeds; this probe discards its response at the caller boundary.
It is not an actual network outage or simulator crash.
"""
import hashlib
import argparse
import json
import time
from carla_safety_agent.batch_catalog import BatchCatalog
from carla_safety_agent.experiment_dispatch import advance_queue
from carla_safety_agent.experiment_matrix import canonical
from carla_safety_agent.experiment_queue import ExperimentQueue
from carla_safety_agent.session import SessionJournal
from regression_scene_versions import ROOT, request
from regression_rule_move import ACTIVE, wait_terminal
from validate_completed_batch import validate


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stop-retry',action='store_true',help='Explicitly stop the recovered first launch, then retry its job')
    args=parser.parse_args()
    assert request('system/preflight')['ready']
    assert request('batches/scheduler')['scheduler']['state'] != 'running'
    plan=request('scenario/compile',{'description':'Town04 前车急刹','max_duration_s':1})
    variant=lambda value:{'id':'baseline','configuration':value}
    dimensions={'scenes':[variant({'scenario':plan['scenario'],
        'scenario_sha256':hashlib.sha256(canonical(plan['scenario'])).hexdigest()})],
        'models':[variant({'action':'rule-run'})], 'weather':[variant({})],
        'textures':[variant({})], 'seeds':[731,732]}
    batch=request('batches/create',dimensions)['batch_id']
    catalog=BatchCatalog(ROOT/'data/experiment-queues')
    queue=ExperimentQueue(catalog.directory(batch));journal=SessionJournal(ROOT/'data')
    report={'state':'failed','batch_id':batch,'scope':__doc__}
    launches=[]
    def transport(path,data=None):
        response=request(path,data)
        if path=='e2e/start':
            launches.append(response['execution_id'])
            raise OSError('injected: successful launch response discarded')
        return response
    try:
        try:advance_queue(queue,journal,ROOT/'.runtime/generated-scenarios',transport)
        except OSError as exc:assert 'response discarded' in str(exc)
        else:raise AssertionError('Response fault did not occur')
        assert len(launches)==1
        jobs=catalog.read(batch)['jobs'];first=jobs[0]
        assert first['state']=='reserved' and len(first['attempts'])==1
        assert not jobs[1]['attempts']
        def no_launch(path,data=None):
            assert path!='e2e/start','Recovery must not repeat native launch'
            return request(path,data)
        recovered=advance_queue(queue,journal,ROOT/'.runtime/generated-scenarios',no_launch)
        assert recovered['action']=='recover_binding' and recovered['bound']
        assert recovered['execution_id']==launches[0]
        if args.stop_retry:request('scenario/stop',{'run_id':launches[0]})
        terminal=wait_terminal(launches[0]);assert terminal['state']==('stopped' if args.stop_retry else 'completed')
        result=advance_queue(queue,journal,ROOT/'.runtime/generated-scenarios',no_launch)
        assert result['action']=='reconcile' and result['state']==terminal['state']
        original_attempt=catalog.read(batch)['jobs'][0]['attempts'][0]
        if args.stop_retry:
            queue.retry(first['job_id'])
            assert catalog.read(batch)['jobs'][0]['state']=='pending'
        queue.set_paused(True)
        assert advance_queue(queue,journal,ROOT/'.runtime/generated-scenarios',no_launch)['action']=='paused'
        assert not catalog.read(batch)['jobs'][1]['attempts']
        queue.set_paused(False)
        deadline=time.monotonic()+180
        while time.monotonic()<deadline:
            result=advance_queue(queue,journal,ROOT/'.runtime/generated-scenarios',request)
            if result['action']=='no_pending_jobs':break
            assert result['action'] in ('started','reconcile'),result
            time.sleep(.5)
        else:raise AssertionError('Resumed batch did not finish')
        result=validate(batch)
        assert [row['attempt_count'] for row in result['verified']]==([2,1] if args.stop_retry else [1,1])
        assert (result['verified'][0]['execution_id']!=launches[0]) == args.stop_retry
        assert catalog.read(batch)['jobs'][0]['attempts'][0]==original_attempt
        report.update(state='verified',result=result,recovered_execution=launches[0],
            launch_not_repeated=True,pause_preserved_second_job=True,stopped_job_retried=args.stop_retry,
            original_attempt_preserved=True)
    finally:
        session=request('session/status')['session']
        attempts={a['attempt_id'] for j in catalog.read(batch)['jobs'] for a in j['attempts']}
        if session.get('configuration',{}).get('request',{}).get('batch_attempt_id') in attempts and session['state'] in ACTIVE:
            request('scenario/stop',{'run_id':session['run_id']});wait_terminal(session['run_id'])
        import carla
        from carla_safety_agent.world_health import observe_idle
        client=carla.Client('127.0.0.1',2000);client.set_timeout(10)
        report['after']=observe_idle(client,client.get_world().get_map().name)
        path=ROOT/'runs/validation'/('batch-lost-response-'+batch+'.json')
        path.write_text(json.dumps(report,indent=2));print(path,flush=True)


if __name__=='__main__':main()

"""Observe a model to terminal route state; do not equate execution with driving success."""
import argparse
import json
from pathlib import Path
import time
import math
from urllib.error import HTTPError
from regression_e2e_lifecycle import request, wait_idle


def motion_observation(telemetry,elapsed):
    """Bounded observations, not a frame-complete driving trace or simulator time."""
    def number(value):
        return value if type(value) in (int,float) and math.isfinite(value) else None
    inputs=telemetry.get('inputs') or {}
    controller=(telemetry.get('outputs') or {}).get('controller') or {}
    return {'frame':telemetry['frame'],'observed_wall_elapsed_s':elapsed,
            'speed_mps':number(inputs.get('speed_mps')),
            **{key:number(controller.get(key)) for key in ('steer','throttle','brake','desired_speed_mps')}}


def acceptance_outcome(report):
    """Execution success alone does not prove this single route was completed."""
    if report.get('cleanup_confirmed') is not True:
        return {'passed': False, 'reason': 'cleanup_unverified', 'exit_code': 1}
    if report.get('natural_terminal') is not True:
        return {'passed': False, 'reason': 'route_not_naturally_terminal', 'exit_code': 2}
    if report.get('execution_healthy') is not True or report.get('error'):
        return {'passed': False, 'reason': 'execution_failed', 'exit_code': 1}
    results = report.get('final_results')
    checkpoint = results.get('_checkpoint') if isinstance(results, dict) else None
    records = checkpoint.get('records') if isinstance(checkpoint, dict) else None
    if not isinstance(records, list) or len(records) != 1 or not isinstance(records[0], dict):
        return {'passed': False, 'reason': 'route_result_unverified', 'exit_code': 1}
    record = records[0]
    scores = record.get('scores')
    completion = scores.get('score_route') if isinstance(scores, dict) else None
    if (record.get('route_id') != 'RouteScenario_' + str(report.get('route')) + '_rep0'
            or type(completion) not in (int, float) or not math.isfinite(completion)):
        return {'passed': False, 'reason': 'route_result_unverified', 'exit_code': 1}
    passed = record.get('status') in ('Completed', 'Perfect') and completion == 100
    return {'passed': passed, 'reason': 'route_completed' if passed else 'route_incomplete',
            'exit_code': 0 if passed else 1,
            'scope': 'single route completion and healthy exit; not collision-free driving or overall acceptance'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model',choices=['vad','tcp','admlp','uniad-tiny','uniad-base'],required=True)
    parser.add_argument('--route',default='26406')
    parser.add_argument('--timeout',type=int,default=600)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if not 60<=args.timeout<=7200:parser.error('timeout must be 60..7200')
    args.output.mkdir(parents=True,exist_ok=False)
    assert request('system/preflight')['ready']
    catalog=request('e2e/benchmark/catalog')
    collection=next(c['path'] for c in catalog['routes']['collections'] if c['name']=='bench2drive220.xml')
    report={'model':args.model,'route':args.route,'natural_terminal':False,'execution_healthy':None,
            'scope':'natural route termination; driving scores retained separately','frames':[],
            'motion_observations':[],'observation_scope':'5-second polling; not all frames; wall elapsed is not simulation time'}
    execution=None;started=time.monotonic()
    try:
        assert request('e2e/start',dict(action='preset-run',algorithm=args.model,collection=collection,route_id=args.route))['ok']
        execution=request('session/status')['session']['run_id'];report['execution_id']=execution
        while time.monotonic()-started<args.timeout:
            session=request('session/status')['session']
            assert session['run_id']==execution,'Execution ownership changed'
            if session['state'] in ('completed','failed','stopped'):
                report['natural_terminal']=session['state']!='stopped'
                report['session']=session
                result=request('e2e/status')
                report['job']=result['job'];report['results']=result.get('results')
                report['preflight']=request('system/preflight')
                report['execution_healthy']=session['state']=='completed' and report['preflight']['ready']
                break
            telemetry=request('e2e/telemetry').get('telemetry')
            if telemetry and (not report['frames'] or telemetry['frame']!=report['frames'][-1]):
                report['frames'].append(telemetry['frame'])
                report['motion_observations'].append(motion_observation(telemetry,time.monotonic()-started))
            print(json.dumps({'execution_id':execution,'state':session['state'],'frame':report['frames'][-1] if report['frames'] else None}),flush=True)
            time.sleep(5)
        else:report['error']='Observation deadline reached; route completion not proven'
    except Exception as error:
        report['error']=error.read().decode('utf-8','replace') if isinstance(error,HTTPError) else str(error)
        raise
    finally:
        try:
            if execution:
                current=request('session/status')['session']
                if current['run_id']==execution and current['state'] in ('preparing','running','stopping'):
                    request('e2e/stop',{'run_id':execution});report['deadline_cleanup']=wait_idle()
                current=request('session/status')['session']
                if current['run_id']!=execution:raise RuntimeError('Execution changed before final result collection')
                final=request('e2e/status')
                report['final_session']=current
                report['final_job']=final['job']
                report['final_results']=final.get('results')
                report['post_exit_preflight']=request('system/preflight')
                report['cleanup_confirmed']=current['state'] in ('completed','stopped') and not current.get('error') and report['post_exit_preflight']['ready']
        except Exception as cleanup_error:
            report['cleanup_confirmed']=False
            report['cleanup_observation_error']=str(cleanup_error)
        report['elapsed_s']=time.monotonic()-started
        report['acceptance']=acceptance_outcome(report)
        (args.output/'report.json').write_text(json.dumps(report,indent=2))
        print(json.dumps({'report':str(args.output/'report.json'),'natural_terminal':report['natural_terminal'],'execution_healthy':report['execution_healthy']}),flush=True)
    return report['acceptance']['exit_code']


if __name__=='__main__':raise SystemExit(main())

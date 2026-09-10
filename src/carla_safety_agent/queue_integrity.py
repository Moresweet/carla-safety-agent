"""Validate persisted scheduler ownership; never repair ambiguous attempts."""
from .scene_store import finite_number, identifier


def validate_ledger(state):
    if not isinstance(state,dict) or state.get('schema_version')!='carla-experiment-queue/1':
        raise ValueError('Invalid queue schema')
    if type(state.get('paused',False)) is not bool:raise ValueError('Invalid queue pause state')
    plan=state.get('plan');jobs=state.get('jobs')
    if not isinstance(plan,dict) or not isinstance(plan.get('jobs'),list) or not isinstance(jobs,list):
        raise ValueError('Invalid queue jobs')
    if not all(isinstance(job,dict) for job in jobs+plan['jobs']):raise ValueError('Invalid queue job record')
    ids=[job.get('job_id') for job in jobs]
    if ids!=[job.get('job_id') for job in plan['jobs']]:raise ValueError('Queue job order differs from plan')
    for job_id in ids:identifier(job_id)
    if len(set(ids))!=len(ids):raise ValueError('Duplicate queue job')
    attempts_seen=set();executions_seen=set();active=0
    terminal={'completed','failed','stopped'}
    for job in jobs:
        status=job.get('state');attempts=job.get('attempts')
        if status not in terminal|{'pending','reserved','running'}:raise ValueError('Unknown queue state')
        if not isinstance(attempts,list) or len(attempts)>20:raise ValueError('Invalid queue attempt count')
        if status in ('reserved','running'):active+=1
        if status!='pending' and (not attempts or not isinstance(attempts[-1],dict) or attempts[-1].get('state')!=status):
            raise ValueError('Job and attempt states differ')
        if status=='pending' and attempts and (not isinstance(attempts[-1],dict) or attempts[-1].get('state') not in ('failed','stopped')):
            raise ValueError('Pending retry still has a live or completed attempt')
        for index,attempt in enumerate(attempts):
            if not isinstance(attempt,dict):raise ValueError('Invalid queue attempt')
            aid=identifier(attempt.get('attempt_id'))
            if aid in attempts_seen:raise ValueError('Duplicate queue attempt identity')
            attempts_seen.add(aid)
            phase=attempt.get('state');execution=attempt.get('execution_id')
            result=attempt.get('result')
            if result is not None and not isinstance(result,dict):raise ValueError('Invalid attempt result')
            if isinstance(result,dict) and result.get('execution') is not None and not isinstance(result['execution'],dict):
                raise ValueError('Invalid attempt execution evidence')
            if phase not in terminal|{'reserved','running'}:raise ValueError('Invalid attempt state')
            if index<len(attempts)-1 and phase not in ('failed','stopped'):
                raise ValueError('Unresolved or completed historical attempt')
            if phase=='reserved' and execution is not None:raise ValueError('Reserved attempt has a bound execution')
            if phase in ('running','completed') and execution is None:raise ValueError('Bound attempt lacks execution')
            if execution is not None:
                identifier(execution)
                if execution in executions_seen:raise ValueError('Execution bound to multiple attempts')
                executions_seen.add(execution)
            created=attempt.get('created_at')
            if not finite_number(created) or created<0:raise ValueError('Invalid attempt creation timestamp')
            if phase in terminal:
                ended=attempt.get('ended_at')
                if not finite_number(ended) or ended<created or not isinstance(attempt.get('result'),dict):
                    raise ValueError('Invalid terminal attempt evidence')
    if active>1:raise ValueError('Multiple active attempts in one serial queue')

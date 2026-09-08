"""Read-only batch accounting; unknown driving/data outcomes stay unknown."""
from collections import Counter
import hashlib
from .experiment_matrix import canonical, compile_matrix


def summarize_queue(state):
    plan = state['plan']
    if compile_matrix(plan['dimensions']) != plan or hashlib.sha256(canonical(plan)).hexdigest() != state['plan_sha256']:
        raise ValueError('Queue plan identity mismatch')
    configurations = {j['job_id']: j['configuration'] for j in plan['jobs']}
    jobs = state['jobs']
    if len(jobs) != len(configurations) or {j['job_id'] for j in jobs} != set(configurations):
        raise ValueError('Queue jobs differ from plan')
    rows = []
    for job in jobs:
        config = configurations[job['job_id']]
        status = job['state']
        if status not in ('pending', 'reserved', 'running', 'completed', 'failed', 'stopped'):
            raise ValueError('Unknown queue state')
        attempts = job['attempts']
        latest = attempts[-1] if attempts else None
        if status != 'pending' and (latest is None or latest['state'] != status):
            raise ValueError('Job and attempt states differ')
        # A retried pending job must not inherit the previous attempt's outcome.
        result = (latest.get('result') or {}) if latest and status != 'pending' else {}
        execution = result.get('execution') or {}
        if execution and execution.get('run_id') != latest.get('execution_id'):
            raise ValueError('Report execution identity mismatch')
        rows.append({'job_id': job['job_id'],
            'variants': {axis: config[axis]['id'] for axis in ('scenes','models','weather','textures')},
            'seed': config['seeds'], 'execution_state': status, 'attempt_count': len(attempts),
            'execution_id': latest.get('execution_id') if latest and status != 'pending' else None,
            'benchmark_passed': result.get('benchmark_passed') if result.get('source') == 'session_journal' else None,
            'data_quality_verified': None,
            'error': execution.get('error') or result.get('error'),
            'result_reference': (execution.get('configuration') or {}).get('results'),
            'attempt_ids': [a['attempt_id'] for a in attempts]})
    counts = dict(Counter(r['execution_state'] for r in rows))
    return {'schema_version': 'carla-experiment-report/1', 'plan_sha256': state['plan_sha256'],
            'paused': state.get('paused', False), 'job_count': len(rows), 'state_counts': counts,
            'all_executions_completed': counts.get('completed', 0) == len(rows), 'rows': rows,
            'limitations': ['Execution completion is not driving success',
                'Data quality is not verified by this summary', 'No statistical A/B conclusion is computed']}

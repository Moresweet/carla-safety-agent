"""Read-only batch accounting; unknown driving/data outcomes stay unknown."""
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
from .experiment_matrix import canonical, compile_matrix


def compare_variants(report, axis, baseline, candidate):
    """Paired descriptive differences; no statistical or causal conclusion."""
    axes = ('scenes', 'models', 'weather', 'textures')
    if axis not in axes or baseline == candidate:
        raise ValueError('Choose one axis and two distinct variants')
    groups = {}
    for row in report['rows']:
        variant = row['variants'][axis]
        if variant not in (baseline, candidate):
            continue
        key = (row['seed'], *(row['variants'][a] for a in axes if a != axis))
        group = groups.setdefault(key, {})
        if variant in group:
            raise ValueError('Ambiguous duplicate comparison condition')
        group[variant] = row
    if not groups:
        raise ValueError('No matching variants in report')
    pairs = []
    for key, group in groups.items():
        a, b = group.get(baseline), group.get(candidate)
        pair = {'seed': key[0], 'fixed_variants': dict(zip((x for x in axes if x != axis), key[1:])),
                'baseline_job_id': a['job_id'] if a else None,
                'candidate_job_id': b['job_id'] if b else None, 'comparable': False}
        if a is None or b is None:
            pair['reason'] = 'Missing paired variant'
        elif any(r['execution_state'] != 'completed' or not r.get('metrics') or r.get('metrics_error') for r in (a, b)):
            pair['reason'] = 'Both executions need verified completed metrics'
        elif a['metrics']['elapsed_s'] != b['metrics']['elapsed_s']:
            pair['reason'] = 'Different observed durations'
        else:
            deltas = {}
            for metric in ('min_ttc_s', 'min_distance_m', 'risk_score'):
                av, bv = a['metrics'][metric], b['metrics'][metric]
                deltas[metric] = None if av is None or bv is None else bv-av
            pair.update(comparable=True, candidate_minus_baseline=deltas,
                        baseline_collision=a['metrics']['collision'], candidate_collision=b['metrics']['collision'])
        pairs.append(pair)
    return {'axis': axis, 'baseline': baseline, 'candidate': candidate,
            'pairs': pairs, 'comparable_count': sum(p['comparable'] for p in pairs),
            'conclusion': 'Descriptive matched differences only; no statistical significance or causal claim'}


def verified_rule_metrics(execution, results_root):
    if execution.get('kind') not in ('rule-run', 'run') or execution.get('state') != 'completed':
        raise ValueError('Metrics require a completed native scenario execution')
    config = execution['configuration']
    root = Path(results_root).resolve()
    raw = Path(config['results'])
    path = raw.resolve()
    if raw.is_symlink() or path.parent != root or path.stat().st_size > 8*1024*1024:
        raise ValueError('Invalid rule result path or size')
    result = json.loads(path.read_text())
    if result.get('execution_id') != execution['run_id'] or result.get('scenario_sha256') != config['scenario_sha256']:
        raise ValueError('Rule result execution/scenario identity mismatch')
    if hashlib.sha256(canonical(result['scenario'])).hexdigest() != config['scenario_sha256']:
        raise ValueError('Rule result scenario contents changed')
    if execution['kind'] == 'run':
        if result.get('schema_version') != 'carla-safety-evaluation/0.1':
            raise ValueError('Unsupported native evaluation result schema')
        scenario_id = result['scenario']['scenario_id']
        result = result['result']
        if result.get('scenario_id') != scenario_id:
            raise ValueError('Nested result scenario identity mismatch')
    if result.get('status') not in ('passed', 'failed') or not isinstance(result.get('collision'), bool):
        raise ValueError('Invalid driving outcome')
    metrics = {}
    for key in ('min_ttc_s', 'min_distance_m', 'elapsed_s', 'risk_score'):
        value = result[key]
        if value is None and key in ('min_ttc_s', 'min_distance_m'):
            metrics[key] = None
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError('Invalid driving metric')
        metrics[key] = value
    reasons = result.get('failure_reasons')
    if not isinstance(reasons, list) or not all(isinstance(v, str) for v in reasons):
        raise ValueError('Invalid driving failure reasons')
    return {**metrics, 'collision': result['collision'], 'failure_reasons': reasons,
            'benchmark_passed': result['status'] == 'passed', 'source': str(path)}


def summarize_queue(state, results_root=None):
    from .queue_integrity import validate_ledger
    validate_ledger(state)
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
        if execution:
            request = execution.get('configuration', {}).get('request', {})
            if (request.get('batch_job_id') != job['job_id'] or
                    request.get('batch_attempt_id') != latest['attempt_id']):
                raise ValueError('Execution belongs to another batch job or attempt')
        rows.append({'job_id': job['job_id'],
            'variants': {axis: config[axis]['id'] for axis in ('scenes','models','weather','textures')},
            'seed': config['seeds'], 'execution_state': status, 'attempt_count': len(attempts),
            'execution_id': latest.get('execution_id') if latest and status != 'pending' else None,
            'benchmark_passed': result.get('benchmark_passed') if result.get('source') == 'session_journal' else None,
            'data_quality_verified': None,
            'error': execution.get('error') or result.get('error'),
            'result_reference': (execution.get('configuration') or {}).get('results'),
            'attempt_ids': [a['attempt_id'] for a in attempts]})
        if results_root is not None and execution.get('kind') in ('rule-run', 'run') and status == 'completed':
            try:
                selected_root = results_root[execution['kind']] if isinstance(results_root, dict) else results_root
                metrics = verified_rule_metrics(execution, selected_root)
                rows[-1].update(metrics=metrics, benchmark_passed=metrics['benchmark_passed'])
            except (ValueError, KeyError, TypeError, OSError) as exc:
                rows[-1].update(metrics_error=str(exc), benchmark_passed=None)
    counts = dict(Counter(r['execution_state'] for r in rows))
    return {'schema_version': 'carla-experiment-report/1', 'plan_sha256': state['plan_sha256'],
            'paused': state.get('paused', False), 'job_count': len(rows), 'state_counts': counts,
            'all_executions_completed': counts.get('completed', 0) == len(rows), 'rows': rows,
            'limitations': ['Execution completion is not driving success',
                'Data quality is not verified by this summary', 'No statistical A/B conclusion is computed']}

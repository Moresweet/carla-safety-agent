"""One resumable scheduler step; no hidden background loop or automatic retry."""
import fcntl
from .experiment_scenario import materialize_scenario
from .batch_capabilities import supported_configuration


def advance_queue(queue, journal, scenario_root, request):
    with (queue.root/'dispatch.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {'action': 'dispatcher_busy'}
        return _advance(queue, journal, scenario_root, request)


def _advance(queue, journal, scenario_root, request):
    state = queue.read()
    active = next((j for j in state['jobs'] if j['state'] in ('reserved', 'running')), None)
    if active:
        attempt = active['attempts'][-1]['attempt_id']
        if active['state'] == 'reserved':
            return {'action': 'recover_binding', **queue.recover_binding(active['job_id'], attempt, journal)}
        return {'action': 'reconcile', **queue.reconcile(active['job_id'], attempt, journal)}
    if state.get('paused', False):
        return {'action': 'paused'}
    if not any(j['state'] == 'pending' for j in state['jobs']):
        return {'action': 'no_pending_jobs', 'states': [j['state'] for j in state['jobs']]}
    preflight = request('system/preflight')
    if not preflight.get('ready'):
        return {'action': 'preflight_blocked', 'checks': preflight.get('checks', [])}
    claim = queue.claim()
    if claim is None:
        return {'action': 'not_claimed'}
    job_id, attempt = claim['job_id'], claim['attempt']['attempt_id']
    try:
        config = claim['configuration']
        model = config['models']['configuration']
        if not supported_configuration(model):
            raise ValueError('Batch dispatcher model adapter is not implemented for this configuration')
        plan = materialize_scenario(scenario_root, {'job_id': job_id, 'configuration': config})
    except (ValueError, KeyError, TypeError) as exc:
        queue.update_attempt(job_id, attempt, outcome='failed', result={'phase': 'prepare', 'error': str(exc)})
        return {'action': 'preparation_failed', 'job_id': job_id, 'error': str(exc)}
    options = {**model, 'route': plan['scenario_path'],
               'scenario_sha256': plan['scenario_sha256'], 'unified_capture': True,
               'batch_job_id': job_id, 'batch_attempt_id': attempt}
    # Any transport/response failure keeps the reservation. The next step only
    # looks up the persisted attempt; it must not blindly dispatch again.
    response = request('e2e/start', options)
    execution = journal.find_batch_attempt(attempt, job_id)
    if not execution or execution['run_id'] != response.get('execution_id'):
        raise ValueError('Launch response has no matching persisted execution')
    queue.update_attempt(job_id, attempt, execution_id=execution['run_id'])
    return {'action': 'started', 'job_id': job_id, 'execution_id': execution['run_id']}

"""Explicit, ID-scoped batch controls shared by the local HTTP interface."""
from .experiment_dispatch import advance_queue
from .experiment_queue import ExperimentQueue
from .scene_store import identifier


def control_batch(catalog, data, journal, scenario_root, request):
    if not isinstance(data, dict):
        raise ValueError('Batch control must be an object')
    action = data.get('action')
    if action not in ('advance', 'pause', 'resume', 'retry'):
        raise ValueError('Unknown batch control action')
    required = {'batch_id', 'action'} | ({'job_id'} if action == 'retry' else set())
    if set(data) != required:
        raise ValueError('Unexpected or missing batch control fields')
    if action == 'retry':
        identifier(data['job_id'])
    batch_id = data['batch_id']
    catalog.read(batch_id)  # Refuse corrupt or untrusted plans before mutation.
    queue = ExperimentQueue(catalog.directory(batch_id))
    if action in ('pause', 'resume'):
        result = {**queue.set_paused(action == 'pause'), 'dispatched': False}
    elif action == 'retry':
        queue.retry(data['job_id'])
        result = {'job_id': data['job_id'], 'requeued': True, 'dispatched': False}
    else:
        result = advance_queue(queue, journal, scenario_root, request)
    return {'ok': True, 'batch_id': batch_id, **result}

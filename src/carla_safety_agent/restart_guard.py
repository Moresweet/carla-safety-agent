"""Fail closed before a caller intentionally terminates the local bridge."""
from .session import observed_process_identity


def verify_asset_jobs_idle(status):
    if (not isinstance(status, dict) or status.get('schema_version') != 'asset-restart/1'
            or not isinstance(status.get('unresolved'), list)):
        raise ValueError('Asset job status unknown; inspect before bridge restart')
    if status['unresolved']:
        raise ValueError('Asset generation/import unresolved; inspect before bridge restart')


def verify_asset_endpoint(fetch, local_status, *, legacy_upgrade=False):
    from urllib.error import HTTPError
    try:
        status = fetch('blender/restart-status')
    except HTTPError as exc:
        if not legacy_upgrade or exc.code != 404:
            raise
        status = local_status()
    else:
        # Identified old GET catch-all, not a healthy asset-status response.
        # Require root AND an unpredictable absent route to match before using
        # local evidence. Any malformed/new/error response still fails closed.
        legacy_health = {'ok': True, 'service': 'carla-surface-bridge'}
        if legacy_upgrade and status == legacy_health:
            import uuid
            if (fetch('') != legacy_health or
                    fetch('__legacy_probe_' + uuid.uuid4().hex) != legacy_health):
                raise ValueError('Legacy bridge fingerprint mismatch')
            status = local_status()
    verify_asset_jobs_idle(status)


def verify_dataset_jobs_idle(status):
    required={'recovery','excerpt','quality','archive'}
    if not isinstance(status,dict) or status.get('schema_version')!='dataset-jobs/1' or not isinstance(status.get('active'),dict) or set(status['active'])!=required:
        raise ValueError('Dataset job status unknown; inspect before bridge restart')
    if any(value is not None for value in status['active'].values()):
        raise ValueError('Dataset background job active; wait before bridge restart')


def verify_handoff_idle(handoff):
    if not isinstance(handoff,dict) or handoff.get('state') not in ('idle','restored','failed_before_switch','acknowledged'):
        raise ValueError('Map handoff active, interrupted or unknown; inspect it before routine bridge restart')


def verify_idle(session, scheduler, observe=observed_process_identity):
    if not isinstance(scheduler, dict) or scheduler.get('state') not in (
            'idle', 'completed', 'cancelled', 'paused', 'needs_attention'):
        raise ValueError('Batch scheduler active or unknown; cancel scheduling before restart')
    if not isinstance(session, dict) or session.get('state') not in ('idle', 'completed', 'failed', 'stopped'):
        raise ValueError('Simulation active or unknown; stop it before bridge restart')
    identity = session.get('process')
    if identity is not None:
        if not isinstance(identity, dict) or set(identity) != {'pid', 'start_ticks'}:
            raise ValueError('Invalid process identity; refusing restart')
        if observe(identity['pid']) == identity:
            raise ValueError('Recorded execution process is still alive')


def verify_crash_restart(session, scheduler, native_alive, port_open,
                         observe=observed_process_identity):
    """Permit bridge replacement without falsifying the durable recovering state."""
    if native_alive or port_open:
        raise ValueError('Native process or simulator port is still alive')
    if not isinstance(session, dict) or session.get('state') != 'recovering':
        verify_idle(session, scheduler, observe)
        return
    # Reuse all scheduler and process-identity protections. Only a dead server's
    # recovery state is relaxed in this local check, never in the journal.
    verify_idle({**session, 'state':'failed'}, scheduler, observe)


def verify_recovery_restart(session, scheduler, observe=observed_process_identity):
    """Reload recovery code only after the recorded worker has exited."""
    if not isinstance(session, dict) or session.get('state') != 'recovering':
        raise ValueError('Recovery restart requires a recovering session')
    verify_idle({**session, 'state': 'failed'}, scheduler, observe)

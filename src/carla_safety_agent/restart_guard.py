"""Fail closed before a caller intentionally terminates the local bridge."""
from .session import observed_process_identity


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

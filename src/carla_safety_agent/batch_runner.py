"""Run explicit serial scheduler steps, stopping on uncertainty or failure."""
def run_batch(step, wait, *, cancelled=lambda: False, observe=lambda result: None):
    while not cancelled():
        result = step()  # Transport errors propagate; never blindly retry launch.
        observe(result)
        action = result.get('action')
        if action == 'no_pending_jobs':
            states = result.get('states', [])
            return {'state': 'completed' if states and all(s == 'completed' for s in states)
                    else 'needs_attention', 'last_step': result}
        if action == 'reconcile' and result.get('reconciled') and result.get('state') in ('failed', 'stopped'):
            return {'state': 'needs_attention', 'last_step': result}
        if action == 'recover_binding' and not result.get('bound'):
            return {'state': 'needs_attention', 'last_step': result}
        if action not in ('started', 'reconcile', 'recover_binding'):
            return {'state': 'paused' if action == 'paused' else 'needs_attention', 'last_step': result}
        # Interruptible pacing, including after completion, before another claim.
        wait()
    return {'state': 'cancelled', 'current_simulation_stopped': False}

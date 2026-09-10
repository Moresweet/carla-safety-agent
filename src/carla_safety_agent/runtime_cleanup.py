"""Best-effort completion of every owned cleanup step, with visible failures."""
import time


class Cleanup:
    def __init__(self):
        self.errors = []

    def attempt(self, label, operation, *, reports_errors=False):
        try:
            result = operation()
            if reports_errors and result:
                self.errors.extend(f'{label}: {error}' for error in result)
            return True
        except Exception as exc:
            self.errors.append(f'{label}: {exc}')
            return False

    def finish(self):
        if self.errors:
            raise RuntimeError('Runtime cleanup incomplete: '+ '; '.join(self.errors))


def cleanup_native_runtime(carla, client, world, original, actors, capture, rig, agent):
    cleanup = Cleanup()
    if capture:
        cleanup.attempt('Capture', capture.close, reports_errors=True)
    if rig:
        cleanup.attempt('Model sensors', rig.destroy)
    if agent:
        cleanup.attempt('Model', agent.destroy)
    for actor in actors:
        if getattr(actor, 'type_id', '').startswith('sensor.'):
            cleanup.attempt(f'Sensor {actor.id} stop', actor.stop)
    if actors:
        # IDs belong to this executor only. Batch destruction also tolerates
        # already-deleted actors; post-run native checks verify actual absence.
        cleanup.attempt('Owned actors', lambda: client.apply_batch(
            [carla.command.DestroyActor(actor.id) for actor in actors]))
    cleanup.attempt('World settings', lambda: world.apply_settings(original))
    cleanup.finish()


def cleanup_rule_runtime(carla, client, world, original, actors, capture,
                         recorder, result, error, render):
    cleanup = Cleanup()
    if capture:
        cleanup.attempt('Unified capture', capture.close, reports_errors=True)
    for actor in actors:
        def stop(actor=actor):
            if not actor.is_alive: return
            if actor.type_id.startswith('sensor.'):
                actor.stop()
            elif actor.type_id.startswith('vehicle.'):
                actor.set_autopilot(False)
        cleanup.attempt(f'Actor {actor.id} stop', stop)
    if render:
        time.sleep(.25)  # Existing streaming-thread image-write drain window.
    if recorder:
        cleanup.attempt('Recorder finalization', lambda: recorder.finalize(result,error))
    cleanup.attempt('Callback drain', lambda: world.tick() if world.get_settings().synchronous_mode else None)
    if actors:
        cleanup.attempt('Owned actors', lambda: client.apply_batch(
            [carla.command.DestroyActor(actor.id) for actor in actors]))
    cleanup.attempt('World settings', lambda: world.apply_settings(original))
    cleanup.finish()

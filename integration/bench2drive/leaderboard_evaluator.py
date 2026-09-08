"""Project-owned cancellation-safe launcher for the installed evaluator."""
import signal
import sys

# A detached bridge can inherit SIG_IGN from its launching shell. Restore this
# before importing torch or CARLA, rather than waiting for evaluator setup.
signal.signal(signal.SIGINT, signal.default_int_handler)

from leaderboard import leaderboard_evaluator as upstream


active_evaluator = None


class CancellationSafeEvaluator(upstream.LeaderboardEvaluator):
    def __init__(self, *args, **kwargs):
        global active_evaluator
        active_evaluator = self
        self._agent_watchdog = None
        self._client_timed_out = False
        super().__init__(*args, **kwargs)
        from carla_safety_agent.sensor_capture import capture_agent
        entry = self.module_agent.get_entry_point()
        setattr(self.module_agent, entry, capture_agent(getattr(self.module_agent, entry)))

    def _cleanup(self):
        # Upstream destroys the ego (and its children) before agent.destroy().
        # Release our auxiliary sensors first, while their handles are valid.
        agent = getattr(self, 'agent_instance', None)
        capture = getattr(agent, '_capture', None)
        if capture is not None:
            try:
                capture.close()
                # CARLA's actor snapshot can still contain just-destroyed sensors
                # until the next frame. Upstream enumerates and destroys those
                # handles again; advance once here in the sole evaluator owner.
                world = getattr(self, 'world', None)
                if world is not None:
                    if world.get_settings().synchronous_mode:
                        world.tick()
                    else:
                        world.wait_for_tick(5.0)
            except Exception as exc:
                print(f'Capture cleanup: {exc}', flush=True)
            finally:
                agent._capture = None
        return super()._cleanup()

    def _signal_handler(self, signum, frame):
        if not getattr(self.manager, '_running', False):
            # The upstream handler only clears _running, which run_scenario
            # later sets back to True; cancellation during setup is then lost.
            raise KeyboardInterrupt
        super()._signal_handler(signum, frame)


upstream.LeaderboardEvaluator = CancellationSafeEvaluator

if __name__ == '__main__':
    try:
        upstream.main()
    except KeyboardInterrupt:
        print('Evaluation cancelled during initialization', flush=True)
        if active_evaluator is not None:
            for method in ('_cleanup', '_reset_world_settings'):
                if method == '_cleanup' and getattr(active_evaluator, 'world', None) is None:
                    continue
                try:
                    getattr(active_evaluator, method)()
                except Exception as exc:
                    print(f'Cancellation cleanup {method}: {exc}', flush=True)
        sys.exit(130)

"""Pre-restart check; unavailable/legacy status endpoints require manual review."""
from carla_safety_agent.restart_guard import verify_idle
from regression_scene_versions import request


if __name__ == '__main__':
    verify_idle(request('session/status')['session'],
                request('batches/scheduler')['scheduler'])
    print('Bridge idle check passed; no active batch scheduler or execution')

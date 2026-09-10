"""Spawn an explicitly owned but unregistered prop; verify unknown across restart."""
import json
import subprocess
import uuid
import carla
from regression_scene_versions import ROOT, request
from carla_safety_agent.world_health import observe_idle


def main():
    assert request('system/preflight')['ready']
    assert request('batches/scheduler')['scheduler']['state'] != 'running'
    session = request('session/status')['session']['run_id']
    client = carla.Client('127.0.0.1', 2000); client.set_timeout(10)
    world = client.get_world()
    before = observe_idle(client, world.get_map().name, seconds=1)
    actor = None
    output = ROOT/'runs/validation'/('object-origin-'+uuid.uuid4().hex+'.json')
    report = {'before': before, 'state': 'failed'}
    try:
        # Direct native creation intentionally bypasses editor provenance.
        actor = world.spawn_actor(world.get_blueprint_library().find('static.prop.advertisement'),
            carla.Transform(carla.Location(x=393.098, y=-228.088, z=2.5)))
        report['actor_id'] = actor.id
        world.wait_for_tick(5)
        for restart in (False, True):
            if restart:
                subprocess.run(['bash', 'scripts/restart_studio_bridge.sh'], cwd=ROOT, check=True)
            rows = request(f'catalog/objects?category=spawned_props&origin=unknown&q={actor.id}')['objects']
            assert any(row['id'] == actor.id and row['origin'] == 'unknown' for row in rows)
            rows = request(f'catalog/objects?category=spawned_props&origin=existing&q={actor.id}')['objects']
            assert not any(row['id'] == actor.id for row in rows)
        node = '/home/moresweet/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node'
        result = subprocess.run([node, 'tools/browser_reviewed_models.mjs', '--unknown-actor', str(actor.id)],
            cwd=ROOT, text=True, capture_output=True, timeout=180)
        report['browser_stdout'] = result.stdout
        report['browser_stderr'] = result.stderr
        result.check_returncode()
        report['state'] = 'verified'
    finally:
        assert client.get_world().id == before['episode']
        assert request('session/status')['session']['run_id'] == session
        if actor is not None:
            replies = client.apply_batch_sync([carla.command.DestroyActor(actor.id)], False)
            assert len(replies) == 1 and not replies[0].error
            assert world.wait_for_tick(5).find(actor.id) is None
        report['after'] = observe_idle(client, before['map'])
        output.write_text(json.dumps(report, indent=2))
        print(output, flush=True)


if __name__ == '__main__':
    main()

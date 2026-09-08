"""Opt-in native rule-run edit regression; cleans up only its own prop."""
import json
import time
from pathlib import Path

from regression_scene_versions import ROOT, request

ACTIVE = ('preparing', 'running', 'stopping', 'recovering')


def wait_terminal(execution):
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        session = request('session/status')['session']
        if session['run_id'] != execution:
            raise RuntimeError('Execution ownership changed; refusing cleanup')
        if session['state'] not in ACTIVE:
            return session
        time.sleep(.5)
    raise RuntimeError('Execution not terminal; retaining test prop')


def main():
    import carla
    assert request('system/preflight')['ready']
    client = carla.Client('127.0.0.1', 2000)
    client.set_timeout(10)
    world = client.get_world()
    assert world.get_map().name.endswith('Town04')
    prop_id = execution = None
    try:
        prop = request('objects/spawn', {'blueprint_id': 'static.prop.advertisement',
            'transform': {'location': {'x': 240., 'y': -350., 'z': 2.5}}})['object']
        prop_id = prop['id']
        assert prop['origin'] == 'user'
        plan = request('scenario/compile', {'description': 'Town04 前车急刹，自车5 m/s',
                                            'max_duration_s': 20})
        request('e2e/start', {'action': 'rule-run', 'route': plan['scenario_path'],
            'scenario_sha256': plan['scenario_sha256'], 'unified_capture': True})
        execution = request('session/status')['session']['run_id']
        deadline = time.monotonic() + 90
        dataset = None
        while time.monotonic() < deadline:
            for path in (ROOT/'.runtime/generated-scenarios').glob('capture-*/manifest.json'):
                manifest = json.loads(path.read_text())
                if manifest.get('execution_id') == execution and manifest['frame_count'] >= 5:
                    dataset = path.parent
                    break
            if dataset:
                break
            assert request('session/status')['session']['state'] in ACTIVE
            time.sleep(.5)
        assert dataset, 'No recording created'
        moved = request('objects/update', {'actor_id': prop_id,
                          'transform': {'location': {'x': 245.}}})
        assert moved['object']['origin'] == 'user', moved
        # Read a subsequent native snapshot, not the cached command response pose.
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            location = world.get_actor(prop_id).get_location()
            if abs(location.x - 245.) < .02:
                break
            time.sleep(.1)
        assert abs(location.x - 245.) < .02, location
        request('scenario/stop', {'run_id': execution})
        session = wait_terminal(execution)
        assert session['state'] == 'stopped', session
        result = json.loads(Path(session['configuration']['results']).read_text())
        records = [json.loads(p.read_text()) for p in Path(result['editor_commands']).glob('*.json')]
        updates = [r for r in records if (r.get('command') or {}).get('action') == 'update']
        assert len(updates) == 1 and updates[0]['response']['ok'], updates
        event = updates[0]
        assert event['execution_id'] == execution
        assert event['observed_frame_before'] == event['observed_frame_after']
        assert not world.get_settings().synchronous_mode
        assert not list(world.get_actors().filter('sensor.*'))
        report = {'execution_id': execution, 'dataset': str(dataset), 'actor_id': prop_id,
                  'origin': moved['object']['origin'], 'native_x': location.x,
                  'boundary_frame': event['observed_frame_before'], 'passed': True,
                  'limitations': ['Does not prove rendered texture or image/pose alignment']}
    finally:
        if execution:
            session = request('session/status')['session']
            if session['run_id'] != execution:
                raise RuntimeError(f'Ownership changed; retaining test actor {prop_id}')
            if session['state'] in ACTIVE:
                request('scenario/stop', {'run_id': execution})
                wait_terminal(execution)
        if prop_id is not None:
            request('objects/delete', {'actor_id': prop_id})
            # This observer may retain an old actor cache: confirm with a fresh
            # snapshot after async restoration, without taking tick ownership.
            world = client.get_world()
            snapshot = world.wait_for_tick(10)
            assert snapshot is not None and snapshot.find(prop_id) is None
    report['test_actor_removed'] = True
    output = ROOT/'runs/validation'/f'rule-move-{execution}.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2))
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()

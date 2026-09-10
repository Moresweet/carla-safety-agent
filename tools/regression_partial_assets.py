"""Bounded native test: fail the second generated prop, retain and clean the first."""
import json
import time
import uuid
from types import SimpleNamespace

import carla

from carla_safety_agent.carla_adapter import CarlaAdapter
from carla_safety_agent.world_health import observe_idle
from regression_material_slots import ROOT, request


def main():
    assert request('/system/preflight')['ready']
    assert request('/batches/scheduler')['scheduler']['state'] != 'running'
    session = request('/session/status')['session']['run_id']
    client = carla.Client('127.0.0.1', 2000)
    client.set_timeout(10)
    world = client.get_world()
    before = observe_idle(client, world.get_map().name, seconds=1)
    output = ROOT/'runs/validation'/('partial-assets-'+uuid.uuid4().hex+'.json')
    owned = []
    report = {'state': 'started', 'before': before, 'cases': []}
    # Use an existing map spawn location as a placement reference; no ego needed.
    reference = SimpleNamespace(get_location=lambda: world.get_map().get_spawn_points()[0].location)
    try:
        for shape in ('metal_pipes', 'concrete_barriers'):
            actors = []
            class FailingWorld:
                def __init__(self): self.calls = 0
                def get_map(self): return world.get_map()
                def get_blueprint_library(self): return world.get_blueprint_library()
                def try_spawn_actor(self, *args):
                    self.calls += 1
                    if self.calls == 2:
                        return None  # Deterministic partial failure, no server mutation.
                    actor = world.try_spawn_actor(*args)
                    if actor:
                        owned.append(actor)  # Independent test safety ledger.
                    return actor
            proxy = FailingWorld()
            spec = SimpleNamespace(shape=shape, dimensions_m=(2, .4, .4), mass_kg=0,
                                   count=2, distance_ahead_m=20, lateral_offset_m=0)
            try:
                CarlaAdapter._spawn_generated_asset(carla, proxy, reference, spec, actors)
            except RuntimeError as exc:
                assert 'failed to spawn generated' in str(exc)
            else:
                raise AssertionError('Expected second-spawn failure')
            assert proxy.calls == 2 and len(actors) == 1 and actors[0] is owned[-1]
            deadline = time.monotonic()+5
            while not world.get_snapshot().find(actors[0].id) and time.monotonic()<deadline:
                time.sleep(.05)
            assert world.get_snapshot().find(actors[0].id), 'Partial actor disappeared before parent cleanup'
            report['cases'].append({'shape': shape, 'partial_actor_id': actors[0].id,
                                    'retained_by_parent': True})
            responses = client.apply_batch_sync([carla.command.DestroyActor(actors[0].id)], False)
            assert len(responses) == 1 and not responses[0].error
        report['state'] = 'verified'
    except BaseException as exc:
        report.update(state='failed', error=str(exc))
        raise
    finally:
        try:
            assert request('/session/status')['session']['run_id'] == session and client.get_world().id == before['episode']
            responses = client.apply_batch_sync([carla.command.DestroyActor(a.id) for a in owned], False)
            assert len(responses) == len(owned)
            assert all(not r.error or r.error == 'unable to destroy actor: not found' for r in responses)
            report['after'] = observe_idle(client, before['map'])
            snapshot = world.get_snapshot()
            assert all(snapshot.find(a.id) is None for a in owned)
        except BaseException as exc:
            report.update(state='recovery_failed', cleanup_error=str(exc))
            raise
        finally:
            output.write_text(json.dumps(report, indent=2))
            print(output, flush=True)


if __name__ == '__main__':
    main()

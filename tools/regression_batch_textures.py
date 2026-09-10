"""Opt-in baseline/exact-road-slot batch; preserves pre-existing editor overrides."""
import argparse
import hashlib
import json
import time
import uuid
from carla_safety_agent.batch_catalog import BatchCatalog
from carla_safety_agent.experiment_matrix import canonical
from carla_safety_agent.material_library import MaterialLibrary
from carla_safety_agent.session import SessionJournal
from regression_scene_versions import ROOT, request
from regression_batch_queue import restore_test_weather
from validate_completed_batch import validate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', choices=['rule-run','vad','tcp','admlp','uniad-tiny','uniad-base'], default='rule-run')
    parser.add_argument('--near-road', action='store_true', help='Choose the nearest spawn to the exact road bounding-box center before dispatch')
    parser.add_argument('--target', default='Road_Road_Town04_1')
    args = parser.parse_args()
    assert request('system/preflight')['ready']
    assert request('batches/scheduler')['scheduler']['state'] != 'running'
    import carla
    client = carla.Client('127.0.0.1',2000); client.set_timeout(10)
    world = client.get_world()
    assert world.get_map().name.split('/')[-1] == 'Town04'
    original_view = world.get_spectator().get_transform()
    materials = MaterialLibrary(ROOT/'data')
    before = materials.overrides(world.id)
    digest = 'c18aa91a7294c909c4f13b642aadeb13b4d2968a687a351f3ad99e8503a6dce7'
    materials.texture(digest)
    target = args.target
    assert target in materials.catalog(world.get_map().name)['actors'], 'Target has no exported catalog'
    paint = {'environment_materials':[{'target':target,
        'component':'StaticMeshComponent0','slot':0,'texture':digest}]}
    assert not any(r['target']==target and r['texture']==digest for r in before.values()), 'Fixture must differ from baseline'
    plan = request('scenario/compile', {'description':'Town04 前车急刹，自车 5 m/s','max_duration_s':1})
    if args.near_road:
        roads = [obj for obj in world.get_environment_objects(carla.CityObjectLabel.Roads)
                 if obj.name in (target,target+'_SM_0',target+'_SM')]
        assert len(roads)==1, 'Exact road identity is ambiguous or missing'
        center = roads[0].bounding_box.location
        points = world.get_map().get_spawn_points()
        spawn_index = min(range(len(points)),key=lambda i:points[i].location.distance(center))
        assert points[spawn_index].location.distance(center)<100, 'No nearby tested spawn point'
        plan['scenario']['ego']['spawn_index']=spawn_index
    variant = lambda identity, config: {'id':identity,'configuration':config}
    dimensions = {'scenes':[variant('scene', {'scenario':plan['scenario'],
        'scenario_sha256':hashlib.sha256(canonical(plan['scenario'])).hexdigest()})],
        'models':[variant(args.model, {'action':'rule-run'} if args.model=='rule-run' else {'action':'run','algorithm':args.model})],
        'weather':[variant('same',{})], 'textures':[variant('current',{}),variant('road-checker',paint)], 'seeds':[31]}
    batch_id = request('batches/create',dimensions)['batch_id']
    catalog, journal = BatchCatalog(ROOT/'data/experiment-queues'), SessionJournal(ROOT/'data')
    output = ROOT/'runs/validation'/('batch-textures-'+uuid.uuid4().hex+'.json')
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps({'batch_id':batch_id,'state':'created','before':before}))
    started = request('batches/scheduler',{'batch_id':batch_id,'action':'start'})['scheduler']
    observed = set()
    deadline = time.monotonic()+1200
    while True:
        status = request('batches/scheduler')['scheduler']
        assert status['scheduler_id']==started['scheduler_id'], 'Scheduler ownership changed'
        current = request('session/status')['session']
        recovery = current.get('configuration',{}).get('texture_recovery')
        if recovery and current['state']=='running':
            assert recovery['episode']==world.id
            if any(r['target']==target and r['texture']==digest for r in materials.overrides(world.id).values()):
                observed.add(current['run_id'])
        if status['state']!='running': break
        if time.monotonic()>deadline: raise RuntimeError('Batch still owned; inspect it without starting another execution')
        time.sleep(.2)
    assert status['state']=='completed', status
    result = validate(batch_id)
    state = catalog.read(batch_id)
    assert materials.overrides(world.id)==before, 'Editor material overrides were not restored'
    assert not world.get_settings().synchronous_mode
    assert not list(world.get_actors().filter('sensor.*'))
    records = [journal.read_execution(j['attempts'][-1]['execution_id']) for j in state['jobs']]
    assert records[0]['configuration']['texture_recovery'] is None
    recovery = records[1]['configuration']['texture_recovery']
    assert recovery['before']==list(before.values())
    assert records[1]['run_id'] in observed, 'No applied texture record observed during execution'
    restore_test_weather(state, request('session/status')['session'], journal, world)
    world.get_spectator().set_transform(original_view)
    result.update(model=args.model, target=target, spawn_index=plan['scenario']['ego']['spawn_index'],
        restored_editor_overrides=True, applied_observed=sorted(observed),
        async_and_sensors_clean=True, visual_review_required=True)
    output.write_text(json.dumps(result,indent=2))
    print(json.dumps({'report':str(output),**result}),flush=True)


if __name__=='__main__': main()

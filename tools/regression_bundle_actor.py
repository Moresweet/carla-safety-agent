"""Native bundle restore of a deleted user prop; preserve unrelated actors."""
import json
import argparse
from pathlib import Path
import tempfile
import uuid

from carla_safety_agent.project_bundle import export_bundle, import_bundle, prepare_generated_assets
from carla_safety_agent.blender_package import read_asset
from regression_scene_versions import ROOT, request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--blueprint', default='static.prop.advertisement')
    parser.add_argument('--source-package', type=Path)
    args = parser.parse_args()
    if bool(args.source_package) != args.blueprint.startswith('generated.prop.'):
        parser.error('Generated blueprints require an explicit source package, and vice versa')
    if args.source_package: read_asset(args.source_package)
    assert request('system/preflight')['ready']
    assert request('batches/scheduler')['scheduler']['state'] != 'running'
    baseline = request('scenes/save', {'name':'对象迁移验证前基线'})
    baseline_ids = {obj['stable_id'] for obj in baseline['document']['objects']}
    owned = set(); stable = None
    try:
        prop = request('objects/spawn', {'blueprint_id':args.blueprint,
            'transform':{'location':{'x':393.098,'y':-228.088,'z':2.5}}})['object']
        owned.add(prop['id'])
        saved = request('scenes/save', {'name':'用户对象迁移验证'})
        added = [obj for obj in saved['document']['objects'] if obj['stable_id'] not in baseline_ids]
        assert len(added) == 1
        target = added[0]; stable = target['stable_id']
        folder = ROOT/'data/project-bundles'; folder.mkdir(parents=True,exist_ok=True)
        bundle_id = uuid.uuid4().hex
        archive = folder/(bundle_id+'.zip')
        export_bundle(ROOT/'data/scenes',ROOT/'data',[saved['head']['scene_id']],archive,
                      generated_assets={args.blueprint:args.source_package} if args.source_package else None)
        source_report = None
        if args.source_package:
            isolated = Path(tempfile.mkdtemp(prefix='bundle-generated-', dir=ROOT/'runs/validation'))
            imported_project = import_bundle(archive, isolated)
            prepared = prepare_generated_assets(archive, imported_project)
            prepared_job = prepared['assets'][args.blueprint]
            _, source_files = read_asset(args.source_package)
            assert all((Path(prepared_job['directory'])/name).read_bytes()==payload
                       for name,payload in source_files.items())
            assert not (imported_project/'.runtime/blender-assets/registry.json').exists()
            source_report = {'isolated_project':str(imported_project),'prepared':prepared,
                             'source_bytes_verified':True,'target_unreal_import_verified':False}
        request('objects/delete', {'actor_id':prop['id']}); owned.remove(prop['id'])
        restored = request('scenes/restore-bundle', {'bundle_id':bundle_id,
            'scene_id':saved['head']['scene_id'],'version':saved['head']['version']})
        replacement = restored['bindings'][stable]; owned.add(replacement)
        assert replacement != prop['id'] and restored['spawned'] == 1
        import carla
        client = carla.Client('127.0.0.1',2000); client.set_timeout(10)
        world = client.get_world(); actor = world.get_actor(replacement)
        if args.source_package:
            from carla_safety_agent.blender_pipeline import BlenderPipeline
            assert actor.type_id == 'static.prop.mesh'
            assert actor.attributes['mesh_path'] == BlenderPipeline(ROOT).registry()[args.blueprint]['mesh_path']
        else:
            assert actor.type_id == target['blueprint_id']
        location = actor.get_location()
        assert all(abs(getattr(location,key)-value)<.02 for key,value in target['transform']['location'].items())
        second = request('scenes/restore-bundle', {'bundle_id':bundle_id,
            'scene_id':saved['head']['scene_id'],'version':saved['head']['version']})
        assert second['spawned'] == 0 and second['bindings'][stable] == replacement
        observed = request('scenes/save', {'name':'用户对象迁移后快照'})['document']
        assert {obj['stable_id'] for obj in observed['objects']} == baseline_ids|{stable}
        result = {'passed':True,'bundle_id':bundle_id,'stable_id':stable,
            'source_package_migration':source_report,
            'original_actor':prop['id'],'restored_actor':replacement,
            'position_verified':True,'repeat_restore_did_not_duplicate':True}
    finally:
        # If a response was lost, recover ownership from the stable ID, not proximity.
        if stable:
            observed = request('scenes/save', {'name':'对象迁移清理检查'})['document']
            if any(obj['stable_id']==stable for obj in observed['objects']):
                from carla_safety_agent.provenance import ActorProvenance
                import carla
                client = carla.Client('127.0.0.1',2000); client.set_timeout(10)
                world = client.get_world()
                records = ActorProvenance(ROOT/'.runtime/actor-provenance.json').records(world.id)
                owned.update(int(actor_id) for actor_id,record in records.items()
                             if record.get('stable_id')==stable and world.get_actor(int(actor_id)))
        for actor_id in owned: request('objects/delete', {'actor_id':actor_id})
        request('scenes/restore', {'scene_id':baseline['head']['scene_id'],'version':baseline['head']['version']})
    after = request('scenes/save', {'name':'对象迁移清理后快照'})['document']
    assert {obj['stable_id'] for obj in after['objects']} == baseline_ids
    result['test_actor_removed'] = True
    output = ROOT/'runs/validation'/('bundle-actor-'+bundle_id+'.json')
    output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True)


if __name__ == '__main__': main()

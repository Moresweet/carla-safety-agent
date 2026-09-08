"""Opt-in source-package import to a NEW Unreal asset and native spawn test."""
import argparse
import json
import uuid
from pathlib import Path

from carla_safety_agent.blender_package import import_asset
from carla_safety_agent.blender_pipeline import BlenderPipeline
from regression_material_slots import ROOT, request


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',type=Path)
    parser.add_argument('--registered-job',help='Resume spawn verification without repeating asset import')
    parser.add_argument('--expected-size',nargs=3,type=float,metavar=('X','Y','Z'),
                        help='Optional expected native bounding-box dimensions in metres')
    args=parser.parse_args()
    assert request('/system/preflight')['ready']
    assert request('/batches/scheduler')['scheduler']['state']!='running'
    pipeline=BlenderPipeline(ROOT)
    if args.registered_job:
        assert args.registered_job.isalnum()
        job={'job_id':args.registered_job}
        matches=[entry for entry in pipeline.registry().values()
                 if Path(entry['source_fbx']).parent==pipeline.runtime/args.registered_job]
        assert len(matches)==1
        imported=matches[0];asset_name=imported['asset_id']
    else:
        job=import_asset(args.archive,ROOT)
        asset_name='CSA_MigratedBarrier_'+uuid.uuid4().hex[:10]
        print(json.dumps({'phase':'importing','job_id':job['job_id'],'asset_name':asset_name}),flush=True)
        imported=pipeline.import_to_carla(job['job_id'],asset_name)
    print(json.dumps({'phase':'registered','blueprint_id':imported['blueprint_id'],
                      'warning':imported.get('warning')}),flush=True)
    assert imported['blueprint_id']=='generated.prop.'+asset_name.lower()
    assert pipeline.registry()[imported['blueprint_id']]['mesh_path']==imported['mesh_path']
    assert request('/system/preflight')['ready']
    baseline=request('/scenes/save',{'name':'Blender迁移生成验证前基线'})
    actor_id=None
    output=ROOT/'runs/validation'/('blender-package-'+job['job_id']+'-'+uuid.uuid4().hex[:8]);output.mkdir()
    try:
        spawned=request('/objects/spawn',{'blueprint_id':imported['blueprint_id'],
            'transform':{'location':{'x':393.098,'y':-228.088,'z':2.5}}})
        actor_id=spawned['object']['id']
        import carla
        client=carla.Client('127.0.0.1',2000);client.set_timeout(10)
        world=client.get_world();actor=world.get_actor(actor_id)
        assert actor is not None
        assert actor.attributes.get('mesh_path')==imported['mesh_path']
        assert abs(actor.get_location().x-393.098)<.02
        bounds={key:float(getattr(actor.bounding_box.extent,key))*2 for key in ('x','y','z')}
        print(json.dumps({'phase':'native_bounds','dimensions_m':bounds,'attributes':actor.attributes}),flush=True)
        if args.expected_size:
            assert all(abs(bounds[axis]-size)<.01 for axis,size in zip(('x','y','z'),args.expected_size)), bounds
        request('/focus/actor',{'actor_id':actor_id})
        (output/'spawned.jpg').write_bytes(request('/scene/preview',raw=True))
        result={'passed':True,'job_id':job['job_id'],'blueprint_id':imported['blueprint_id'],
            'mesh_path':imported['mesh_path'],'actor_id':actor_id,'import_warning':imported.get('warning'),
            'import_exit_rechecked':not bool(args.registered_job),
            'import_returncode':imported.get('import_returncode'),
            'import_clean_exit_verified':not bool(args.registered_job) and imported.get('import_returncode')==0,
            'expected_dimensions_m':args.expected_size,
            'scope':'Native actor identity, position and cleanup only; visual rendering not verified',
            'dimensions_m':bounds,
            'retained_unreal_asset':True,'visual_review_required':True}
    finally:
        if actor_id is not None:request('/objects/delete',{'actor_id':actor_id})
        request('/scenes/restore',{'scene_id':baseline['head']['scene_id'],'version':baseline['head']['version']})
    snapshot=world.wait_for_tick(10)
    assert snapshot.find(actor_id) is None
    fresh_client=carla.Client('127.0.0.1',2000);fresh_client.set_timeout(10)
    assert actor_id not in {item.id for item in fresh_client.get_world().get_actors()}
    result['test_actor_removed']=True
    (output/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'output':str(output),**result}),flush=True)


if __name__=='__main__':main()

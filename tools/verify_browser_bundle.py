"""Read-only verification of the package created by browser_reviewed_models QA."""
import argparse
import json
from pathlib import Path
from carla_safety_agent.project_bundle import read_bundle
from carla_safety_agent.scene_store import SceneStore

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report',type=Path)
    parser.add_argument('--require-material-preview',action='store_true')
    parser.add_argument('--native-diagnostic',action='store_true')
    args=parser.parse_args()
    report=json.loads(args.report.read_text())
    exported=ROOT/'data/project-bundles'/(report['exportedId']+'.zip')
    uploaded=ROOT/'data/project-bundles'/(report['uploadedId']+'.zip')
    assert exported.read_bytes()==uploaded.read_bytes()
    manifest,files=read_bundle(uploaded)
    if args.require_material_preview:
        assert any(name.startswith('textures/') for name in files)
        assert any(name.startswith('material-exports/') and not name.endswith('preview-catalog.json') for name in files)
    folder=Path(report['imported'].removeprefix('已隔离导入到：').split('。')[0]).resolve()
    assert folder.parent==ROOT/'data/imported-projects'
    assert json.loads((folder/'manifest.json').read_text())==manifest
    for name,payload in files.items():
        assert (folder/'data'/name).read_bytes()==payload,name
    scene_id=report['sceneId']
    assert SceneStore(folder/'data/scenes').read(scene_id)==SceneStore(ROOT/'data/scenes').read(scene_id)
    if args.native_diagnostic:
        import carla
        from regression_scene_versions import request
        from carla_safety_agent.world_health import observe_idle
        client=carla.Client('127.0.0.1',2000);client.set_timeout(10)
        world=client.get_world()
        before=(world.id,world.get_map().name,{actor.id for actor in world.get_actors()})
        assert not world.get_settings().synchronous_mode
        result=request('projects/bundle/doctor',{'bundle_id':report['uploadedId']})
        current=client.get_world()
        assert before==(current.id,current.get_map().name,{actor.id for actor in current.get_actors()})
        assert result['episode']==str(before[0]) and result['bundle_id']==report['uploadedId']
        assert result['live_world_modified'] is False and result['restore_verified'] is False
        health=observe_idle(client,before[1]);assert health['episode']==before[0]
        args.report.with_name('dependency-verification.json').write_text(json.dumps({'diagnostic':result,'health':health},indent=2))
    print(json.dumps({'verified':True,'file_count':len(files),'isolated_directory':str(folder),
                      'active_scene_matches_export':True,'runtime_dependencies_verified':False}))


if __name__=='__main__':main()

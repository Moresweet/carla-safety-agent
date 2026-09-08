import json
import runpy
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from carla_safety_agent.blender_pipeline import BlenderPipeline


def test_existing_unreal_destination_refused_before_asset_mutation(tmp_path, monkeypatch):
    source = tmp_path/'asset.fbx'; source.write_bytes(b'fixture')
    request = tmp_path/'request.json'
    request.write_text(json.dumps({'fbx_path':str(source),'asset_id':'Existing'}))
    monkeypatch.setenv('CSA_UNREAL_IMPORT_REQUEST',str(request))
    calls = []
    def exists(path): calls.append(path); return True
    monkeypatch.setitem(sys.modules,'unreal',SimpleNamespace(EditorAssetLibrary=SimpleNamespace(does_directory_exist=exists)))
    script = Path(__file__).resolve().parents[1]/'integration/carla/import_generated_asset.py'
    with pytest.raises(RuntimeError,match='already exists'):
        runpy.run_path(str(script))
    assert calls == ['/Game/Carla/Static/Generated/Existing']


def test_old_import_result_cannot_mask_new_failure(tmp_path, monkeypatch):
    pipeline = BlenderPipeline(tmp_path)
    job = pipeline.runtime/'job1'; job.mkdir(parents=True)
    fbx = job/'asset.fbx'; fbx.write_bytes(b'fixture')
    (job/'manifest.json').write_text(json.dumps({'outputs':{'fbx':str(fbx)}}))
    (job/'unreal-import.json').write_text(json.dumps({'blueprint_id':'generated.prop.old'}))
    paths = []
    def failed(*args, **kwargs):
        request = json.loads(Path(kwargs['env']['CSA_UNREAL_IMPORT_REQUEST']).read_text())
        paths.append(request['result_path'])
        return SimpleNamespace(returncode=1,stderr='destination exists',stdout='')
    monkeypatch.setattr('carla_safety_agent.blender_pipeline.subprocess.run',failed)
    for _ in range(2):
        with pytest.raises(RuntimeError,match='destination exists'):
            pipeline.import_to_carla('job1','Existing')
    assert len(set(paths)) == 2
    assert not pipeline.registry_path.exists()

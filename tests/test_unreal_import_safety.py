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
        with pytest.raises(RuntimeError,match='failed with exit 1'):
            pipeline.import_to_carla('job1','Existing')
    assert len(set(paths)) == 2
    assert not pipeline.registry_path.exists()
    logs=list(job.glob('unreal-log-*.json'))
    assert len(logs)==2
    assert all(json.loads(path.read_text())['returncode']==1 for path in logs)
    assert all(json.loads(path.read_text())['stderr_tail']=='destination exists' for path in logs)


@pytest.mark.parametrize('explicit', [False, True])
def test_unclean_exit_never_registers_even_if_result_exists(tmp_path, monkeypatch, explicit):
    pipeline=BlenderPipeline(tmp_path)
    job=pipeline.runtime/'job';job.mkdir(parents=True)
    fbx=job/'asset.fbx';fbx.write_bytes(b'fixture')
    (job/'manifest.json').write_text(json.dumps({'outputs':{'fbx':str(fbx)}}))
    def completed(*args,**kwargs):
        request=json.loads(Path(kwargs['env']['CSA_UNREAL_IMPORT_REQUEST']).read_text())
        Path(request['result_path']).write_text(json.dumps({'blueprint_id':'generated.prop.new'}))
        return SimpleNamespace(returncode=-11,stdout='saved',stderr='shutdown fault')
    monkeypatch.setattr('carla_safety_agent.blender_pipeline.subprocess.run',completed)
    with pytest.raises(RuntimeError,match='exit -11'):
        pipeline.import_to_carla('job','New',**({'require_clean_exit':True} if explicit else {}))
    assert not pipeline.registry_path.exists()
    logs=list(job.glob('unreal-log-*.json'))
    assert logs and json.loads(logs[0].read_text())['stderr_tail']=='shutdown fault'
    assert pipeline.import_attempts()[0]['state']=='needs_attention'


def test_strict_import_rejects_wrong_identity_before_registration(tmp_path, monkeypatch):
    pipeline = BlenderPipeline(tmp_path)
    job = pipeline.runtime/'job'; job.mkdir(parents=True)
    fbx = job/'asset.fbx'; fbx.write_bytes(b'fixture')
    (job/'manifest.json').write_text(json.dumps({'outputs':{'fbx':str(fbx)}}))
    def completed(*args, **kwargs):
        request = json.loads(Path(kwargs['env']['CSA_UNREAL_IMPORT_REQUEST']).read_text())
        Path(request['result_path']).write_text(json.dumps({'ok':True, 'asset_id':'Other',
            'blueprint_id':'generated.prop.other','mesh_path':'/Game/Carla/Static/Generated/Other/SM'}))
        return SimpleNamespace(returncode=0,stdout='saved',stderr='')
    monkeypatch.setattr('carla_safety_agent.blender_pipeline.subprocess.run',completed)
    with pytest.raises(RuntimeError,match='identity mismatch'):
        pipeline.import_to_carla('job','Expected',require_clean_exit=True)
    assert not pipeline.registry_path.exists()

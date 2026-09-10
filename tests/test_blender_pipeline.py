import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from carla_safety_agent.blender_pipeline import BlenderPipeline


def test_normalize_limits_dimensions_and_material(tmp_path: Path):
    pipeline = BlenderPipeline(tmp_path)
    spec = pipeline._normalize({"name": "Barrier", "shape": "cube",
                                "dimensions": [2, 0.4, 5000], "roughness": 2})
    assert spec["dimensions"] == [2.0, 0.4, 1000.0]
    assert spec["roughness"] == 1.0


def test_normalize_requires_real_supported_source(tmp_path: Path):
    pipeline = BlenderPipeline(tmp_path)
    with pytest.raises(ValueError, match="existing FBX"):
        pipeline._normalize({"source_path": str(tmp_path / "missing.fbx")})


def test_pipeline_builds_argument_list_without_shell(monkeypatch, tmp_path: Path):
    worker = tmp_path / "tools" / "blender_asset_worker.py"
    worker.parent.mkdir()
    worker.write_text("pass")
    pipeline = BlenderPipeline(tmp_path, "/opt/blender")

    def run(command, **kwargs):
        assert command[0] == "/opt/blender"
        assert kwargs.get("shell") is None
        output = Path(command[-1])
        (output / "manifest.json").write_text(json.dumps({"ok": True, "outputs": {}}))
        return SimpleNamespace(returncode=0, stdout="done", stderr="")

    monkeypatch.setattr("subprocess.run", run)
    result = pipeline.run({"shape": "sphere", "dimensions": [1, 1, 1]})
    assert result["ok"]
    assert result["job_id"]
    assert pipeline.generation_attempts()[0]['state'] == 'exported'
    assert Path(result['generation_report']).is_file()


@pytest.mark.parametrize('field,value', [('dimensions', [float('nan'), 1, 1]),
    ('dimensions', [True, 1, 1]), ('roughness', float('inf')), ('color', [1, 0, 0]),
    ('color', [1, 0, 0, float('nan')]), ('color', [1, 0, 0, 2])])
def test_invalid_generation_input_never_creates_job(tmp_path, monkeypatch, field, value):
    pipeline = BlenderPipeline(tmp_path)
    monkeypatch.setattr('subprocess.run', lambda *a, **kw: pytest.fail('Must not launch'))
    with pytest.raises(ValueError):
        pipeline.run({field: value})
    assert not pipeline.runtime.exists()


@pytest.mark.parametrize('failure', ['timeout', 'nonzero', 'malformed', 'not_ok'])
def test_generation_failure_retains_report_and_partial_files(tmp_path, monkeypatch, failure):
    import subprocess
    pipeline = BlenderPipeline(tmp_path)
    def run(command, **kwargs):
        output = Path(command[-1])
        assert pipeline.generation_attempts()[0]['state'] == 'generating'
        (output / 'partial.blend').write_bytes(b'partial evidence')
        if failure == 'timeout':
            raise subprocess.TimeoutExpired(command, 180)
        (output / 'manifest.json').write_text('{' if failure == 'malformed' else '{"ok":false}')
        return SimpleNamespace(returncode=1 if failure == 'nonzero' else 0, stdout='', stderr='export failed')
    monkeypatch.setattr('subprocess.run', run)
    with pytest.raises(RuntimeError, match='retained files'):
        pipeline.run({})
    report = pipeline.generation_attempts()[0]
    assert report['state'] == 'needs_attention' and report['error']
    assert not report['automatic_retry'] and not report['live_world_modified']
    assert (Path(report['destination']) / 'partial.blend').read_bytes() == b'partial evidence'
    assert not pipeline.registry_path.exists()
    assert BlenderPipeline(tmp_path).generation_attempts() == [report]


def test_generation_intent_write_failure_never_launches(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError('disk unavailable')
    monkeypatch.setattr('carla_safety_agent.owned_resources.durable_write', fail)
    monkeypatch.setattr('subprocess.run', lambda *a, **kw: pytest.fail('Must not launch'))
    with pytest.raises(OSError, match='disk unavailable'):
        BlenderPipeline(tmp_path).run({})


def test_corrupt_generation_history_is_retained(tmp_path):
    pipeline = BlenderPipeline(tmp_path)
    folder = pipeline.runtime / 'job'
    folder.mkdir(parents=True)
    report = folder / 'generation.json'
    report.write_text('{')
    with pytest.raises(ValueError):
        pipeline.generation_attempts()
    assert report.read_text() == '{'


@pytest.mark.parametrize('failure',[None,'nonzero','identity','corrupt_registry'])
def test_unreal_import_registers_generated_blueprint(monkeypatch, tmp_path: Path, failure):
    pipeline = BlenderPipeline(tmp_path, "/opt/blender")
    pipeline.importer.parent.mkdir(parents=True)
    pipeline.importer.write_text("pass")
    job = pipeline.runtime / "abc123"
    job.mkdir(parents=True)
    fbx = job / "asset.fbx"
    fbx.write_bytes(b"fbx")
    (job / "manifest.json").write_text(json.dumps({
        "name": "Barrier", "outputs": {"fbx": str(fbx)}}))
    if failure=='corrupt_registry':
        pipeline.registry_path.write_text('{broken')

    def run(command, **kwargs):
        assert failure!='corrupt_registry', 'Corrupted registry must stop before Unreal launch'
        import os
        assert len(kwargs['pass_fds'])==1
        os.fstat(kwargs['pass_fds'][0])
        assert any(arg.startswith('-abslog=') for arg in command)
        pending=pipeline.import_attempts()
        assert len(pending)==1 and pending[0]['state']=='importing'
        assert pending[0]['destination']=='/Game/Carla/Static/Generated/Barrier'
        assert pending[0]['import_lock_inherited_by_child'] is True
        request = json.loads(Path(kwargs["env"]["CSA_UNREAL_IMPORT_REQUEST"]).read_text())
        Path(request["result_path"]).write_text(json.dumps({
            "ok": True, "asset_id": "Wrong" if failure=='identity' else "Barrier", "blueprint_id": "generated.prop.barrier",
            "mesh_path": "/Game/Carla/Static/Generated/Barrier/SM_Barrier"}))
        return SimpleNamespace(returncode=1 if failure=='nonzero' else 0, stdout="imported", stderr="")

    monkeypatch.setattr("subprocess.run", run)
    if failure:
        with pytest.raises((RuntimeError,ValueError)):
            pipeline.import_to_carla('abc123')
        if failure=='corrupt_registry':
            assert pipeline.registry_path.read_text()=='{broken'
        else:
            assert not pipeline.registry_path.exists()
        assert pipeline.import_attempts()[0]['state']=='needs_attention'
        return
    result = pipeline.import_to_carla("abc123")
    assert result["blueprint_id"] == "generated.prop.barrier"
    assert pipeline.registry()["generated.prop.barrier"]["mesh_path"].endswith("SM_Barrier")
    assert pipeline.import_attempts()[0]['state']=='registered'
    assert Path(result['import_report']).is_file()


def test_unclean_import_cannot_be_enabled(tmp_path):
    with pytest.raises(ValueError,match='clean process exit'):
        BlenderPipeline(tmp_path).import_to_carla('job',require_clean_exit=False)


def test_native_child_keeps_flock_after_parent_descriptor_closes(tmp_path):
    """Real Linux descriptor inheritance, not an Unreal-crash integration claim."""
    import fcntl
    import subprocess
    import sys
    path=tmp_path/'import.lock'
    lock=path.open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    child=None
    try:
        child=subprocess.Popen([sys.executable,'-c','import sys; sys.stdin.buffer.read(1)'],
            pass_fds=(lock.fileno(),),stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        lock.close()
        with path.open('a') as contender:
            with pytest.raises(BlockingIOError):fcntl.flock(contender,fcntl.LOCK_EX|fcntl.LOCK_NB)
        child.communicate(b'x',timeout=5)
        assert child.returncode==0
        with path.open('a') as contender:fcntl.flock(contender,fcntl.LOCK_EX|fcntl.LOCK_NB)
    finally:
        lock.close()
        if child and child.poll() is None:
            child.terminate();child.wait(timeout=5)


@pytest.mark.parametrize('value',[[], {'generated.prop.test':{}}, {'wrong':{'blueprint_id':'wrong','mesh_path':'/Game/Test'}}])
def test_invalid_registry_is_not_silently_empty(tmp_path,value):
    pipeline=BlenderPipeline(tmp_path)
    pipeline.runtime.mkdir(parents=True)
    pipeline.registry_path.write_text(json.dumps(value))
    with pytest.raises(ValueError,match='invalid entries'):
        pipeline.registry()

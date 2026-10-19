import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from carla_safety_agent.blender_pipeline import BlenderPipeline


def test_restart_lock_rejects_asset_entry_before_job_or_process(tmp_path, monkeypatch):
    import fcntl
    pipeline = BlenderPipeline(tmp_path)
    pipeline.runtime.mkdir(parents=True)
    monkeypatch.setattr('subprocess.run', lambda *a, **kw: pytest.fail('Must not launch'))
    with (pipeline.runtime / 'bridge-restart.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(RuntimeError, match='restart in progress'):
            pipeline.run({})
        with pytest.raises(RuntimeError, match='restart in progress'):
            pipeline.import_to_carla('fixture')
    assert list(pipeline.runtime.iterdir()) == [pipeline.runtime / 'bridge-restart.lock']


def test_generation_child_retains_admission_after_parent_closes(tmp_path, monkeypatch):
    import fcntl
    import subprocess
    import sys
    pipeline = BlenderPipeline(tmp_path)
    children = []
    def launch(command, **kwargs):
        assert len(kwargs['pass_fds']) == 1
        child = subprocess.Popen([sys.executable, '-c', 'import sys; sys.stdin.read()'],
            pass_fds=kwargs['pass_fds'], stdin=subprocess.PIPE)
        children.append(child)
        # Simulate loss of the coordinating call while its child survives.
        raise RuntimeError('coordinator interrupted')
    monkeypatch.setattr('subprocess.run', launch)
    try:
        with pytest.raises(RuntimeError, match='coordinator interrupted'):
            pipeline.run({})
        with (pipeline.runtime / 'bridge-restart.lock').open('a') as lock:
            assert children[0].poll() is None
            with pytest.raises(BlockingIOError):
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            children[0].communicate(timeout=5)
            assert children[0].returncode == 0
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=5)


def test_restart_script_rejects_during_admitted_asset_operation(tmp_path):
    import subprocess
    pipeline = BlenderPipeline(tmp_path)
    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    source = Path(__file__).resolve().parents[1] / 'scripts/restart_studio_bridge.sh'
    (scripts / source.name).write_bytes(source.read_bytes())
    (scripts / 'studio_paths.sh').write_text('# isolated fixture\n')
    with pipeline.operation_admission():
        result = subprocess.run(['bash', str(scripts / source.name), '--stop'],
                                capture_output=True, text=True, timeout=5)
        assert result.returncode != 0
        assert 'Asset operation or bridge restart active' in result.stderr
    result = subprocess.run(['bash', str(scripts / source.name), '--stop'],
                            capture_output=True, text=True, timeout=5)
    assert result.returncode == 0


def test_restart_status_checks_old_generation_beyond_ui_history(tmp_path):
    pipeline = BlenderPipeline(tmp_path)
    for index in range(102):
        job = f'{index:012x}'
        directory = pipeline.runtime / job
        directory.mkdir(parents=True)
        (directory / 'generation.json').write_text(json.dumps({
            'schema_version': 'carla-asset-generation/1', 'job_id': job,
            'attempt_id': job, 'started_at': index,
            'state': 'needs_attention' if index == 0 else 'exported'}))
    before = {p: p.read_bytes() for p in pipeline.runtime.glob('*/generation.json')}
    assert len(pipeline.generation_attempts()) == 100
    assert all(row['state'] == 'exported' for row in pipeline.generation_attempts())
    assert pipeline.restart_status()['unresolved'] == [{
        'job_id': '000000000000', 'attempt_id': '000000000000', 'state': 'needs_attention'}]
    assert all(p.read_bytes() == value for p, value in before.items())


@pytest.mark.parametrize('returncode,ended_at,settled', [
    (0, 2, True), (1, 2, True), (-11, 2, True),
    (True, 2, False), ('0', 2, False), (None, 2, False),
    (0, None, False), (0, float('nan'), False), (0, 0, False)])
def test_restart_failed_generation_requires_explicit_worker_exit(tmp_path, returncode, ended_at, settled):
    pipeline = BlenderPipeline(tmp_path)
    journal = pipeline.runtime / 'abc' / 'generation.json'
    journal.parent.mkdir(parents=True)
    journal.write_text(json.dumps({'schema_version': 'carla-asset-generation/1',
        'job_id': 'abc', 'attempt_id': 'abc', 'started_at': 1,
        'state': 'needs_attention', 'returncode': returncode, 'ended_at': ended_at}))
    before = journal.read_bytes()
    status = pipeline.restart_status()
    assert bool(status['settled_generation_failures']) is settled
    assert bool(status['unresolved']) is not settled
    assert journal.read_bytes() == before
    assert pipeline.generation_attempts()[0]['state'] == 'needs_attention'


@pytest.mark.parametrize('fields,settled', [
    ({}, False), ({'worker_state': 'launching'}, False),
    ({'worker_state': 'not_started'}, True),
    ({'worker_state': 'not_started', 'destination': '/Game/Test'}, False),
    ({'worker_state': 'exited'}, False),
    ({'worker_state': 'exited', 'worker_returncode': True}, False),
    ({'worker_state': 'exited', 'worker_returncode': -11}, True)])
def test_import_restart_requires_explicit_lifecycle_evidence(tmp_path, fields, settled):
    pipeline = BlenderPipeline(tmp_path)
    attempt = 'a' * 32
    journal = pipeline.runtime / 'abc' / f'import-attempt-{attempt}.json'
    journal.parent.mkdir(parents=True)
    journal.write_text(json.dumps({'schema_version': 'carla-asset-import/1',
        'job_id': 'abc', 'attempt_id': attempt, 'report_path': str(journal),
        'started_at': 1, 'ended_at': 2, 'state': 'needs_attention', **fields}))
    before = journal.read_bytes()
    status = pipeline.restart_status()
    assert bool(status['settled_import_failures']) is settled
    assert bool(status['unresolved']) is not settled
    assert journal.read_bytes() == before


def test_restart_status_corrupt_journal_refused(tmp_path):
    pipeline = BlenderPipeline(tmp_path)
    directory = pipeline.runtime / 'broken'
    directory.mkdir(parents=True)
    (directory / 'generation.json').write_text('{}')
    with pytest.raises(ValueError):
        pipeline.restart_status()


@pytest.mark.parametrize('state', ['preparing', 'generating', 'importing'])
@pytest.mark.parametrize('observed,expected', [(None, 'exited'),
    ({'pid': 123, 'start_ticks': '8'}, 'exited'),
    ({'pid': 123, 'start_ticks': '7'}, 'present')])
def test_attempt_coordinator_observation_is_not_child_completion(monkeypatch, state, observed, expected):
    report = {'state': state, 'owner': {'pid': 123, 'start_ticks': '7'}}
    monkeypatch.setattr('carla_safety_agent.session.observed_process_identity', lambda pid: observed)
    result = BlenderPipeline.observe_attempt(report)
    assert result['state'] == state and 'observation' not in report
    assert result['observation']['coordinator'] == expected
    assert result['observation']['child_state'] == 'unknown'
    assert result['observation']['automatic_retry_allowed'] is False


def test_attempt_observation_permission_error_is_unknown(monkeypatch):
    def denied(pid):
        raise PermissionError('denied')
    monkeypatch.setattr('carla_safety_agent.session.observed_process_identity', denied)
    result = BlenderPipeline.observe_attempt({'state': 'importing', 'owner': {'pid': 123, 'start_ticks': '7'}})
    assert result['observation']['coordinator'] == 'unknown'
    assert result['observation']['requires_attention']
    assert BlenderPipeline.observe_attempt({'state': 'exported'}) == {'state': 'exported'}


@pytest.mark.parametrize('kind', ['generation', 'import'])
def test_real_coordinator_exit_leaves_read_only_uncertain_history(tmp_path, kind):
    import os
    import subprocess
    import sys
    script = '''
import os, sys
from pathlib import Path
from carla_safety_agent.blender_pipeline import BlenderPipeline
p = BlenderPipeline(Path(sys.argv[1]))
if sys.argv[2] == 'generation':
    import carla_safety_agent.blender_pipeline as module
    def interrupted(*args, **kwargs):
        os._exit(37)
    module.subprocess.run = interrupted
    p.run({})
else:
    (p.runtime / 'fixture').mkdir(parents=True)
    def interrupted(job, name, attempt_id, report, save, lock):
        report['state'] = 'importing'
        save()
        os._exit(37)
    p._perform_import = interrupted
    p.import_to_carla('fixture')
'''
    environment = {**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1] / 'src')}
    result = subprocess.run([sys.executable, '-c', script, str(tmp_path), kind],
                            env=environment, capture_output=True, timeout=15)
    assert result.returncode == 37, result.stderr
    pipeline = BlenderPipeline(tmp_path)
    paths = list(pipeline.runtime.glob('*/' + ('generation.json' if kind == 'generation' else 'import-attempt-*.json')))
    assert len(paths) == 1
    before = paths[0].read_bytes()
    read = pipeline.generation_attempts if kind == 'generation' else pipeline.import_attempts
    first = read()
    assert first == read()
    assert first[0]['state'] == ('generating' if kind == 'generation' else 'importing')
    assert first[0]['observation']['coordinator'] == 'exited'
    assert first[0]['observation']['requires_attention'] is True
    assert first[0]['observation']['child_state'] == 'unknown'
    assert first[0]['observation']['automatic_retry_allowed'] is False
    assert paths[0].read_bytes() == before
    assert not pipeline.registry_path.exists()


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
        outputs = {}
        for kind in ('blend', 'glb', 'fbx'):
            path = output / ('asset.' + kind)
            path.write_bytes(b'export fixture')
            outputs[kind] = str(path)
        (output / "manifest.json").write_text(json.dumps({"ok": True, "outputs": outputs}))
        return SimpleNamespace(returncode=0, stdout="done", stderr="")

    monkeypatch.setattr("subprocess.run", run)
    result = pipeline.run({"shape": "sphere", "dimensions": [1, 1, 1]})
    assert result["ok"]
    assert result["job_id"]
    assert pipeline.generation_attempts()[0]['state'] == 'exported'
    assert Path(result['generation_report']).is_file()
    before = Path(result['generation_report']).read_bytes()
    monkeypatch.setattr('subprocess.run', lambda *a, **kw: pytest.fail('Reopen must not launch'))
    reopened = pipeline.exported_asset(result['job_id'])
    assert reopened['reopened'] and reopened['outputs'] == result['outputs']
    assert Path(result['generation_report']).read_bytes() == before
    Path(result['outputs']['fbx']).unlink()
    with pytest.raises(ValueError, match='missing or invalid'):
        pipeline.exported_asset(result['job_id'])


@pytest.mark.parametrize('state', ['preparing', 'generating', 'needs_attention'])
def test_reopen_never_promotes_unconfirmed_generation(tmp_path, state):
    pipeline = BlenderPipeline(tmp_path)
    job = pipeline.runtime / 'fixture'
    job.mkdir(parents=True)
    report = job / 'generation.json'
    report.write_text(json.dumps({'schema_version':'carla-asset-generation/1',
        'job_id':'fixture', 'attempt_id':'fixture', 'state':state}))
    before = report.read_bytes()
    with pytest.raises(ValueError, match='confirmed exports'):
        pipeline.exported_asset('fixture')
    assert report.read_bytes() == before


@pytest.mark.parametrize('field,value', [('dimensions', [float('nan'), 1, 1]),
    ('dimensions', [True, 1, 1]), ('roughness', float('inf')), ('color', [1, 0, 0]),
    ('color', [1, 0, 0, float('nan')]), ('color', [1, 0, 0, 2])])
def test_invalid_generation_input_never_creates_job(tmp_path, monkeypatch, field, value):
    pipeline = BlenderPipeline(tmp_path)
    monkeypatch.setattr('subprocess.run', lambda *a, **kw: pytest.fail('Must not launch'))
    with pytest.raises(ValueError):
        pipeline.run({field: value})
    assert not pipeline.runtime.exists()


@pytest.mark.parametrize('kind', ['blend', 'glb', 'fbx'])
@pytest.mark.parametrize('failure', ['missing', 'empty', 'outside', 'symlink', 'null'])
def test_generation_rejects_incomplete_export(tmp_path, monkeypatch, kind, failure):
    pipeline = BlenderPipeline(tmp_path)
    def run(command, **kwargs):
        output = Path(command[-1])
        outputs = {}
        for extension in ('blend', 'glb', 'fbx'):
            path = output / ('asset.' + extension)
            path.write_bytes(b'partial export')
            outputs[extension] = str(path)
        path = Path(outputs[kind])
        if failure == 'missing':
            path.unlink()
        elif failure == 'empty':
            path.write_bytes(b'')
        elif failure in ('outside', 'symlink'):
            external = tmp_path / ('external.' + kind)
            external.write_bytes(b'not owned by export')
            if failure == 'outside':
                outputs[kind] = str(external)
            else:
                path.unlink()
                path.symlink_to(external)
        else:
            outputs[kind] = None
        (output / 'manifest.json').write_text(json.dumps({'ok': True, 'outputs': outputs}))
        return SimpleNamespace(returncode=0, stdout='', stderr='')
    monkeypatch.setattr('subprocess.run', run)
    with pytest.raises(RuntimeError, match='incomplete'):
        pipeline.run({})
    report = pipeline.generation_attempts()[0]
    assert report['state'] == 'needs_attention'
    assert (Path(report['destination']) / 'manifest.json').exists()
    assert not pipeline.registry_path.exists()


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


@pytest.mark.parametrize('field,value', [('job_id', 'other'), ('attempt_id', 'b'*32),
    ('state', 'success'), ('started_at', True), ('started_at', float('nan')),
    ('started_at', float('inf')), ('report_path', '/unrelated/report.json')])
def test_import_history_rejects_mismatched_record_without_mutation(tmp_path, field, value):
    pipeline = BlenderPipeline(tmp_path)
    folder = pipeline.runtime / 'fixture'
    folder.mkdir(parents=True)
    path = folder / ('import-attempt-' + 'a'*32 + '.json')
    report = {'schema_version': 'carla-asset-import/1', 'attempt_id': 'a'*32,
              'job_id': 'fixture', 'state': 'registered', 'started_at': 1,
              'report_path': str(path)}
    report[field] = value
    path.write_text(json.dumps(report))
    before = path.read_bytes()
    with pytest.raises(ValueError, match='Invalid asset import report'):
        pipeline.import_attempts()
    assert path.read_bytes() == before


def test_import_history_rejects_linked_report(tmp_path):
    pipeline = BlenderPipeline(tmp_path)
    folder = pipeline.runtime / 'fixture'
    folder.mkdir(parents=True)
    external = tmp_path / 'external.json'
    external.write_text('{}')
    (folder / ('import-attempt-' + 'a'*32 + '.json')).symlink_to(external)
    with pytest.raises(ValueError, match='path or size'):
        pipeline.import_attempts()
    assert external.read_text() == '{}'


@pytest.mark.parametrize('failure',[None,'nonzero','identity','corrupt_registry','registry_write'])
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
    if failure=='registry_write':
        import carla_safety_agent.owned_resources as resources
        original_write = resources.durable_write
        def fail_registry(path, document, **kwargs):
            if path == pipeline.registry_path:
                raise OSError('registry disk unavailable')
            return original_write(path, document, **kwargs)
        monkeypatch.setattr(resources, 'durable_write', fail_registry)

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


@pytest.mark.parametrize('fail_error_receipt', [False, True])
@pytest.mark.parametrize('boundary', ['launching', 'exited'])
def test_import_worker_journal_write_failure_preserves_uncertainty(tmp_path, monkeypatch, boundary, fail_error_receipt):
    import carla_safety_agent.owned_resources as resources
    pipeline = BlenderPipeline(tmp_path)
    job = pipeline.runtime / 'fixture'
    job.mkdir(parents=True)
    fbx = job / 'asset.fbx'
    fbx.write_bytes(b'fixture')
    (job / 'manifest.json').write_text(json.dumps({'name': 'Barrier', 'outputs': {'fbx': str(fbx)}}))
    calls = []
    def run(command, **kwargs):
        # The write-ahead intent must exist before any external side effect.
        on_disk = json.loads(next(job.glob('import-attempt-*.json')).read_text())
        assert on_disk['state'] == 'importing'
        assert on_disk['worker_state'] == 'launching'
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout='', stderr='')
    original_write = resources.durable_write
    def fail_boundary(path, document, **kwargs):
        if path.name.startswith('import-attempt-'):
            if ((document.get('state') == 'importing' and document.get('worker_state') == boundary)
                    or (fail_error_receipt and document.get('state') == 'needs_attention')):
                raise OSError('injected journal write failure')
        return original_write(path, document, **kwargs)
    monkeypatch.setattr('subprocess.run', run)
    monkeypatch.setattr(resources, 'durable_write', fail_boundary)
    with pytest.raises(RuntimeError, match='inspect'):
        pipeline.import_to_carla('fixture')
    assert len(calls) == (1 if boundary == 'exited' else 0)
    assert not pipeline.registry_path.exists()
    row = pipeline.import_attempts()[0]
    if fail_error_receipt:
        assert row['state'] == ('preparing' if boundary == 'launching' else 'importing')
    else:
        assert row['state'] == 'needs_attention'
    status = pipeline.restart_status()
    # Only a persisted failure receipt with explicit exit evidence can settle.
    settled = boundary == 'exited' and not fail_error_receipt
    assert bool(status['settled_import_failures']) is settled
    assert bool(status['unresolved']) is not settled


@pytest.mark.parametrize('fail_error_receipt', [False, True])
def test_registered_asset_survives_final_receipt_failure(tmp_path, monkeypatch, fail_error_receipt):
    import carla_safety_agent.owned_resources as resources
    pipeline = BlenderPipeline(tmp_path)
    job = pipeline.runtime / 'fixture'
    job.mkdir(parents=True)
    fbx = job / 'asset.fbx'
    fbx.write_bytes(b'fixture')
    (job / 'manifest.json').write_text(json.dumps({'name': 'Barrier', 'outputs': {'fbx': str(fbx)}}))
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        request = json.loads(Path(kwargs['env']['CSA_UNREAL_IMPORT_REQUEST']).read_text())
        Path(request['result_path']).write_text(json.dumps({'ok': True, 'asset_id': 'Barrier',
            'blueprint_id': 'generated.prop.barrier',
            'mesh_path': '/Game/Carla/Static/Generated/Barrier/SM_Barrier'}))
        return SimpleNamespace(returncode=0, stdout='', stderr='')
    original_write = resources.durable_write
    def fail_receipt(path, document, **kwargs):
        if path.name.startswith('import-attempt-') and (document.get('state') == 'registered'
                or (fail_error_receipt and document.get('state') == 'needs_attention')):
            raise OSError('receipt disk unavailable')
        return original_write(path, document, **kwargs)
    monkeypatch.setattr('subprocess.run', run)
    monkeypatch.setattr(resources, 'durable_write', fail_receipt)
    with pytest.raises(RuntimeError, match='inspect'):
        pipeline.import_to_carla('fixture')
    registered = pipeline.registry_path.read_bytes()
    assert pipeline.registry()['generated.prop.barrier']['import_returncode'] == 0
    row = pipeline.import_attempts()[0]
    assert row['state'] == ('importing' if fail_error_receipt else 'needs_attention')
    assert row['registration_observation']['state'] == 'matching'
    assert row['registration_observation']['native_verified'] is False
    assert Path(row['result_path']).is_file()
    monkeypatch.setattr(resources, 'durable_write', original_write)
    with pytest.raises(RuntimeError, match='already registered'):
        pipeline.import_to_carla('fixture')
    assert len(calls) == 1
    assert pipeline.registry_path.read_bytes() == registered
    duplicate = pipeline.import_attempts()[0]
    assert duplicate['worker_state'] == 'not_started'
    assert duplicate['state'] == 'needs_attention'
    status = pipeline.restart_status()
    assert any(row['attempt_id'] == duplicate['attempt_id']
               for row in status['settled_import_failures'])
    assert all(row['attempt_id'] != duplicate['attempt_id'] for row in status['unresolved'])


@pytest.mark.parametrize('variant,expected', [('matching','matching'), ('absent','absent'),
    ('wrong_attempt','absent'), ('wrong_name','conflict'), ('unclean','conflict'), ('corrupt','unknown')])
def test_registration_inspection_does_not_rewrite_evidence(tmp_path, variant, expected):
    pipeline = BlenderPipeline(tmp_path)
    job = pipeline.runtime / 'fixture'
    job.mkdir(parents=True)
    attempt = 'a'*32
    path = job / ('import-attempt-' + attempt + '.json')
    path.write_text(json.dumps({'schema_version':'carla-asset-import/1', 'attempt_id':attempt,
        'job_id':'fixture', 'state':'needs_attention', 'started_at':1, 'report_path':str(path),
        'asset_name':'Barrier'}))
    key = 'generated.prop.wrong' if variant == 'wrong_name' else 'generated.prop.barrier'
    registry = {key: {'blueprint_id':key, 'import_attempt_id':'b'*32 if variant == 'wrong_attempt' else attempt,
        'import_returncode':1 if variant == 'unclean' else 0,
        'mesh_path':'/Game/Carla/Static/Generated/Barrier/SM_Barrier'}}
    pipeline.registry_path.write_text('{' if variant == 'corrupt' else json.dumps({} if variant == 'absent' else registry))
    before = (path.read_bytes(), pipeline.registry_path.read_bytes())
    observation = pipeline.import_attempts()[0]['registration_observation']
    assert observation['state'] == expected
    assert observation['native_verified'] is False
    assert observation['automatic_retry_allowed'] is False
    assert (path.read_bytes(), pipeline.registry_path.read_bytes()) == before


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

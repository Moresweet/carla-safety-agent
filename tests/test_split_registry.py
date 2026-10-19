import json
from pathlib import Path
import pytest

from carla_safety_agent.dataset_split import verified_split
from carla_safety_agent.split_registry import register_split, registered_split_references
from carla_safety_agent.split_registry import require_no_registered_split_references
from carla_safety_agent.split_registry import registry_mutation_lock


def fixture(tmp_path):
    captures = tmp_path/'captures'
    run = captures/'capture-one'
    run.mkdir(parents=True)
    (run/'manifest.json').write_text(json.dumps({'run_id':run.name, 'status':'saved', 'frame_count':1}))
    (run/'index.json').write_text(json.dumps({'frames':[{'frame':1, 'timestamp':.05}]}))
    source = tmp_path/'approved.json'
    source.write_text(json.dumps(verified_split([{'run_id':run.name, 'scene_group':'explicit-related-variants'}], captures)))
    return captures, source, tmp_path/'registry'


def test_register_is_verified_immutable_idempotent_and_discoverable(tmp_path):
    captures, source, registry = fixture(tmp_path)
    original = source.read_bytes()
    first = register_split(source, registry, captures)
    assert first['created'] and not first['raw_sensor_files_verified']
    assert not register_split(source, registry, captures)['created']
    assert source.read_bytes() == original
    refs = registered_split_references(registry)
    assert refs['complete'] and refs['scanned_files'] == 1
    assert len(refs['references']['capture-one']) == 1
    assert list(registry.iterdir()) == [Path(first['path'])]


def test_changed_source_metadata_refuses_registration(tmp_path):
    captures, source, registry = fixture(tmp_path)
    (captures/'capture-one/index.json').write_text('{"frames":[{"frame":2,"timestamp":0.1}]}')
    with pytest.raises(ValueError, match='changed or inconsistent'):
        register_split(source, registry, captures)
    assert not registry.exists()


def test_uploaded_split_uses_same_verified_immutable_registration(tmp_path):
    from carla_safety_agent.split_registry import register_split_payload
    captures, source, registry = fixture(tmp_path)
    result = register_split_payload(source.read_bytes(), registry, captures)
    assert result['created'] and not result['raw_sensor_files_verified']
    assert not register_split(source, registry, captures)['created']
    assert registered_split_references(registry)['references']['capture-one']


@pytest.mark.parametrize('payload', [b'', b'{', b'{"a":1,"a":2}', b'{"a":NaN}', b'x'*(8*1024**2+1)])
def test_bad_upload_never_publishes(tmp_path, payload):
    from carla_safety_agent.split_registry import register_split_payload
    captures, _, registry = fixture(tmp_path)
    with pytest.raises(ValueError): register_split_payload(payload, registry, captures)
    assert not registry.exists()


def test_existing_tampered_entry_is_not_overwritten_and_refs_retained(tmp_path):
    captures, source, registry = fixture(tmp_path)
    registered = register_split(source, registry, captures)
    path = Path(registered['path'])
    document = json.loads(path.read_text()); document['notes'].append('tampered')
    path.write_text(json.dumps(document)); before = path.read_bytes()
    with pytest.raises(ValueError, match='refusing overwrite'):
        register_split(source, registry, captures)
    assert path.read_bytes() == before and len(list(registry.iterdir())) == 1
    refs = registered_split_references(registry)
    assert not refs['complete'] and refs['references']['capture-one']


@pytest.mark.parametrize('fault', ['partial','broken','symlink','directory'])
def test_uncertain_entries_make_scan_incomplete(tmp_path, fault):
    captures, source, registry = fixture(tmp_path)
    first = register_split(source, registry, captures)
    entry = registry/'unfinished.partial'
    if fault == 'partial': entry.write_bytes(source.read_bytes())
    elif fault == 'broken': entry.write_text('{')
    elif fault == 'symlink': entry.symlink_to(source)
    else: entry.mkdir()
    result = registered_split_references(registry)
    assert not result['complete'] and result['warnings']
    assert result['references']['capture-one']
    assert Path(first['path']).is_file()


def test_missing_registry_is_only_empty_registered_scope_and_limit_is_fail_closed(tmp_path):
    assert registered_split_references(tmp_path/'absent')['references'] == {}
    captures, source, registry = fixture(tmp_path)
    register_split(source, registry, captures)
    (registry/'extra.partial').write_text('{}')
    result = registered_split_references(registry, max_files=1)
    assert not result['complete'] and result['scanned_files'] == 1


def test_cleanup_guard_blocks_references_and_all_uncertain_scans(tmp_path):
    captures, source, registry = fixture(tmp_path)
    register_split(source, registry, captures)
    with pytest.raises(ValueError, match='still references'):
        require_no_registered_split_references(registry, ['capture-one'])
    assert require_no_registered_split_references(registry, ['unrelated'])['complete']
    (registry/'broken.partial').write_text('{')
    with pytest.raises(ValueError, match='incomplete'):
        require_no_registered_split_references(registry, ['unrelated'])
    assert (captures/'capture-one/manifest.json').is_file()


def test_cli_registration_is_discovered_by_inventory_without_explicit_split_flag(tmp_path):
    import os
    import subprocess
    import sys
    captures, source, _ = fixture(tmp_path)
    data = tmp_path/'data'
    (data/'experiment-queues').mkdir(parents=True)
    (data/'project-bundles').mkdir()
    registry = data/'dataset-splits'
    project = Path(__file__).resolve().parents[1]
    env = {**os.environ, 'PYTHONPATH':str(project/'src')}
    original = source.read_bytes()
    command = [sys.executable, str(project/'tools/register_dataset_split.py'), str(source),
               '--dataset-root', str(captures), '--registry', str(registry)]
    registered = json.loads(subprocess.run(command, env=env, check=True, capture_output=True, text=True).stdout)
    assert registered['created']
    output = tmp_path/'inventory.json'
    subprocess.run([sys.executable, str(project/'tools/inventory_capture_storage.py'),
                    '--root', str(captures), '--data-root', str(data), '--output', str(output)],
                   env=env, check=True, capture_output=True)
    receipt = json.loads(output.read_text())
    assert receipt['registered_split_references']['complete']
    assert receipt['recordings'][0]['split_referenced_by'][0]['path'] == registered['path']
    assert source.read_bytes() == original and (captures/'capture-one').is_dir()


def test_other_process_cannot_register_during_cleanup_lock(tmp_path):
    import os
    import subprocess
    import sys
    captures, source, registry = fixture(tmp_path)
    project = Path(__file__).resolve().parents[1]
    command = [sys.executable, str(project/'tools/register_dataset_split.py'), str(source),
               '--dataset-root', str(captures), '--registry', str(registry)]
    env = {**os.environ, 'PYTHONPATH': str(project/'src')}
    with registry_mutation_lock(registry):
        result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=5)
        assert result.returncode != 0 and 'busy' in result.stderr
        assert not registry.exists()
    assert subprocess.run(command, env=env, capture_output=True, timeout=5).returncode == 0
    with registry_mutation_lock(registry):
        with pytest.raises(ValueError, match='still references'):
            require_no_registered_split_references(registry, ['capture-one'])


def test_registration_checks_source_again_after_cleanup_releases_lock(tmp_path):
    captures, source, registry = fixture(tmp_path)
    with registry_mutation_lock(registry):
        # Isolated fixture only: emulate a changed/missing recording, not deletion.
        (captures/'capture-one').rename(captures/'moved-fixture')
    with pytest.raises((ValueError, OSError)):
        register_split(source, registry, captures)
    assert not registry.exists()


def test_lock_release_after_exception_and_symlink_refusal(tmp_path):
    registry = tmp_path/'registry'
    with pytest.raises(ValueError, match='injected'):
        with registry_mutation_lock(registry):
            raise ValueError('injected')
    with registry_mutation_lock(registry):
        pass
    lock = tmp_path/'registry.lock'
    lock.rename(tmp_path/'original.lock')
    lock.symlink_to(tmp_path/'original.lock')
    with pytest.raises(OSError):
        with registry_mutation_lock(registry):
            pytest.fail('Linked lock accepted')

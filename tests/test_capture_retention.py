import json
import pytest
from carla_safety_agent.capture_retention import CaptureRetention


def setup_store(tmp_path):
    root = tmp_path/'captures'
    folder = root/'capture-test'
    folder.mkdir(parents=True)
    (folder/'manifest.json').write_text(json.dumps({'run_id':'capture-test'}))
    return CaptureRetention(tmp_path/'state', root), folder


def test_keep_persists_and_unkeep_does_not_delete_capture(tmp_path):
    store, folder = setup_store(tmp_path)
    first = store.set_keep('capture-test', True, 'key evidence', expected_revision=0)
    assert first['revision'] == 1
    reopened = CaptureRetention(store.root, store.capture_root)
    assert reopened.snapshot()['records']['capture-test']['reason'] == 'key evidence'
    with pytest.raises(ValueError, match='revision changed'):
        store.set_keep('capture-test', False, 'stale request', expected_revision=0)
    final = reopened.set_keep('capture-test', False, 'released', expected_revision=1)
    assert final['records'] == {} and folder.is_dir()


def test_corrupt_state_never_silently_loses_protection(tmp_path):
    store, _ = setup_store(tmp_path)
    store.root.mkdir()
    store.path.write_text('{}')
    with pytest.raises(ValueError): store.snapshot()
    with pytest.raises(ValueError): store.set_keep('capture-test', True, 'keep', expected_revision=0)
    assert store.path.read_text() == '{}'


@pytest.mark.parametrize('run_id,keep,reason,revision', [('../outside',True,'x',0),
    ('capture-test','false','x',0), ('capture-test',True,' ',0),
    ('capture-test',True,'x',True), ('missing',True,'x',0)])
def test_invalid_change_has_no_state_write(tmp_path, run_id, keep, reason, revision):
    store, _ = setup_store(tmp_path)
    with pytest.raises(ValueError): store.set_keep(run_id, keep, reason, expected_revision=revision)
    assert not store.path.exists()


def test_capture_identity_and_links_rejected(tmp_path):
    store, folder = setup_store(tmp_path)
    (folder/'manifest.json').write_text('{"run_id":"other"}')
    with pytest.raises(ValueError): store.set_keep('capture-test', True, 'x', expected_revision=0)
    (store.capture_root/'capture-link').symlink_to(folder, target_is_directory=True)
    with pytest.raises(ValueError): store.set_keep('capture-link', True, 'x', expected_revision=0)

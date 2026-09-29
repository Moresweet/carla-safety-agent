import os
import pytest
from carla_safety_agent.runtime_storage import inventory_runtime


def test_all_runtime_categories_counted_without_reading_payload(tmp_path):
    for category in ('generated-scenarios', 'recovery-staging', 'blender-assets'):
        folder = tmp_path/category
        folder.mkdir()
        (folder/'data').write_bytes(b'x'*8192)
    log = tmp_path/'bridge.log'
    log.write_bytes(b'log')
    expected = sum(p.stat().st_blocks*512 for p in tmp_path.rglob('*') if p.is_file())
    report = inventory_runtime(tmp_path)
    assert report['complete']
    assert report['allocated_bytes'] == expected
    assert len(report['categories']) == 4
    assert report['deletion_approved'] is False


def test_hardlinks_count_once_and_external_link_not_followed(tmp_path):
    source = tmp_path/'data'
    source.write_bytes(b'x'*8192)
    os.link(source, tmp_path/'duplicate')
    report = inventory_runtime(tmp_path)
    assert report['allocated_bytes'] == source.stat().st_blocks*512
    (tmp_path/'link').symlink_to('/does-not-exist')
    os.mkfifo(tmp_path/'pipe')
    report = inventory_runtime(tmp_path)
    assert not report['complete']
    assert len(report['warnings']) == 2
    assert report['allocated_bytes'] == source.stat().st_blocks*512


def test_linked_root_refused(tmp_path):
    (tmp_path/'link').symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError):
        inventory_runtime(tmp_path/'link')


def test_concurrent_runtime_scan_rejected_and_failure_releases(tmp_path, monkeypatch):
    import threading
    import carla_safety_agent.runtime_storage as module
    entered, release = threading.Event(), threading.Event()
    errors = []
    def scan(root):
        entered.set()
        assert release.wait(5)
        raise OSError('injected scan failure')
    monkeypatch.setattr(module, 'inventory_runtime', scan)
    def worker():
        try:
            module.review_runtime(tmp_path)
        except OSError as exc:
            errors.append(str(exc))
    thread = threading.Thread(target=worker)
    thread.start()
    try:
        assert entered.wait(5)
        with pytest.raises(module.RuntimeStorageBusy):
            module.review_runtime(tmp_path)
    finally:
        release.set()
        thread.join(5)
    assert not thread.is_alive()
    assert errors == ['injected scan failure']
    monkeypatch.setattr(module, 'inventory_runtime', lambda root: {'complete': True})
    assert module.review_runtime(tmp_path) == {'complete': True}

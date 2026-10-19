import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location('project_storage_audit', Path(__file__).resolve().parents[1]/'tools/audit_project_storage.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_unvalidated_entries_preserved_and_reported(tmp_path):
    (tmp_path/'unfinished.partial').write_bytes(b'partial')
    (tmp_path/'broken.zip').write_bytes(b'not a zip')
    (tmp_path/'sources').mkdir()
    (tmp_path/'linked.zip').symlink_to(tmp_path/'broken.zip')
    result = module.audit(tmp_path)
    assert not result['complete'] and len(result['archives']) == 4
    assert all(not row['validated'] and row['error'] for row in result['archives'])
    assert (tmp_path/'unfinished.partial').read_bytes() == b'partial'
    assert (tmp_path/'broken.zip').read_bytes() == b'not a zip'
    assert (tmp_path/'linked.zip').is_symlink()


def test_root_link_rejected(tmp_path):
    (tmp_path/'linked').symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError): module.audit(tmp_path/'linked')


def test_source_comparison_is_byte_exact_and_not_validation(tmp_path, monkeypatch):
    staging = tmp_path/(('a'*32)+'-sources'); staging.mkdir()
    final = tmp_path/(('a'*32)+'.zip'); final.write_bytes(b'fixture')
    (staging/'0.zip').write_bytes(b'source')
    monkeypatch.setattr(module, 'read_bundle', lambda path: ({'schema_version':'fixture', 'dependencies':{}},
        {'generated-assets/example.zip':b'source'}))
    result = module.audit(tmp_path)
    row = next(row for row in result['archives'] if row['name'] == staging.name)
    assert not row['validated'] and not result['complete']
    assert row['source_comparison']['all_bytes_duplicated']
    (staging/'0.zip').write_bytes(b'change')
    assert not module.audit_sources(staging)['all_bytes_duplicated']
    (staging/'linked').symlink_to(final)
    with pytest.raises(ValueError): module.audit_sources(staging)


def test_source_comparison_requires_valid_final(tmp_path):
    staging = tmp_path/(('b'*32)+'-sources'); staging.mkdir()
    with pytest.raises(ValueError): module.audit_sources(staging)
    final = tmp_path/(('b'*32)+'.zip'); final.symlink_to('/nonexistent')
    with pytest.raises(ValueError): module.audit_sources(staging)


def test_partial_payload_comparison_keeps_incomplete_status(tmp_path, monkeypatch):
    partial = tmp_path/(('c'*32)+'.partial'); partial.write_bytes(b'partial')
    final = partial.with_suffix('.zip'); final.write_bytes(b'final')
    payloads = {partial: {'scene.json': b'original'},
                final: {'scene.json': b'original', 'runtime/reference.json': b'extra'}}
    monkeypatch.setattr(module, 'read_bundle', lambda path: (
        {'schema_version': 'fixture', 'dependencies': {}}, payloads[path]))
    result = module.audit(tmp_path)
    row = next(row for row in result['archives'] if row['name'] == partial.name)
    assert not result['complete'] and not row['validated']
    assert row['partial_comparison']['all_payloads_duplicated']
    payloads[final]['scene.json'] = b'changed'
    comparison = module.audit_partial(partial)
    assert not comparison['all_payloads_duplicated']
    assert comparison['different_or_missing_entries'] == ['scene.json']
    assert partial.read_bytes() == b'partial' and final.read_bytes() == b'final'


def test_partial_requires_safe_valid_pair(tmp_path):
    partial = tmp_path/(('d'*32)+'.partial'); partial.write_bytes(b'broken')
    with pytest.raises(ValueError): module.audit_partial(partial)
    final = partial.with_suffix('.zip'); final.symlink_to('/nonexistent')
    with pytest.raises(ValueError): module.audit_partial(partial)
    linked = tmp_path/(('e'*32)+'.partial'); linked.symlink_to(partial)
    with pytest.raises(ValueError): module.audit_partial(linked)

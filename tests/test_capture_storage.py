import json
import os

import pytest

from carla_safety_agent.capture_storage import inventory_captures


@pytest.mark.parametrize('name',['../outside','/tmp/absolute','a/b','',True])
def test_single_directory_rejects_unsafe_selection(tmp_path,name):
    with pytest.raises(ValueError):inventory_captures(tmp_path,only_directory=name)


@pytest.mark.parametrize('case',['missing','no-manifest','linked','corrupt'])
def test_single_directory_unknown_is_not_successful_zero(tmp_path,case):
    selected=tmp_path/'selected'
    if case=='linked':selected.symlink_to(tmp_path,target_is_directory=True)
    elif case!='missing':
        selected.mkdir()
        if case=='corrupt':(selected/'manifest.json').write_text('broken')
    result=inventory_captures(tmp_path,only_directory='selected')
    assert not result['complete']


def test_single_directory_scope_explicit_and_excludes_unrelated_errors(tmp_path):
    selected=recording(tmp_path)
    (tmp_path/'unrelated-link').symlink_to('/nonexistent')
    result=inventory_captures(tmp_path,only_directory=selected.name)
    assert result['complete'] and result['only_directory']==selected.name
    assert len(result['recordings'])==1
    assert not inventory_captures(tmp_path)['complete']


def recording(root, name='capture-a'):
    folder = root/name
    folder.mkdir()
    (folder/'manifest.json').write_text(json.dumps({'status':'recording', 'bytes':999999}))
    return folder


def test_measures_blocks_instead_of_trusting_manifest_and_preserves_data(tmp_path):
    folder = recording(tmp_path)
    raw = folder/'raw.bin'
    raw.write_bytes(b'actual bytes')
    before = raw.read_bytes()
    result = inventory_captures(tmp_path)
    row = result['recordings'][0]
    assert result['complete'] and row['declared_bytes'] == 999999
    assert row['allocated_bytes'] == sum(p.stat().st_blocks*512 for p in folder.iterdir())
    assert raw.read_bytes() == before and row['status'] == 'recording'


def test_symlinks_not_followed_and_partial_explicit(tmp_path):
    folder = recording(tmp_path)
    external = tmp_path/'external'
    external.mkdir()
    (external/'large').write_bytes(b'x'*10000)
    (folder/'link').symlink_to(external, target_is_directory=True)
    result = inventory_captures(tmp_path)
    assert not result['complete']
    assert result['scanned_files'] == 1
    assert 'Skipped symlink' in result['recordings'][0]['warnings'][0]


def test_hardlinks_counted_once(tmp_path):
    a = recording(tmp_path, 'a')
    b = recording(tmp_path, 'b')
    (a/'raw').write_bytes(b'x'*4096)
    os.link(a/'raw', b/'raw')
    result = inventory_captures(tmp_path)
    expected = sum(p.stat().st_blocks*512 for p in (a/'manifest.json', b/'manifest.json', a/'raw'))
    assert result['allocated_bytes'] == expected


def test_budget_and_malformed_manifest_not_silently_complete(tmp_path):
    folder = recording(tmp_path)
    (folder/'raw').write_bytes(b'x')
    result = inventory_captures(tmp_path, max_files=1)
    assert not result['complete'] and result['warnings']
    (folder/'manifest.json').write_text('[]')
    result = inventory_captures(tmp_path)
    assert not result['complete'] and result['recordings'][0]['warnings']


def test_rejects_root_link_and_invalid_budget(tmp_path):
    link = tmp_path/'link'
    link.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError): inventory_captures(link)
    with pytest.raises(ValueError): inventory_captures(tmp_path, max_files=True)
    with pytest.raises(ValueError): inventory_captures(tmp_path, max_seconds=float('nan'))


def test_root_entry_link_never_reports_complete(tmp_path):
    external = tmp_path/'outside'; external.mkdir()
    root = tmp_path/'datasets'; root.mkdir()
    (root/'capture-linked').symlink_to(external, target_is_directory=True)
    result = inventory_captures(root)
    assert not result['complete'] and result['scanned_files'] == 0
    assert 'linked root entry' in result['warnings'][0]


@pytest.mark.parametrize('prefix', ['capture-', 'recovered-', 'excerpt-'])
def test_missing_capture_manifest_is_unknown_not_zero(tmp_path, prefix):
    folder = tmp_path/(prefix+'interrupted'); folder.mkdir()
    (folder/'raw.bin').write_bytes(b'partially written sample')
    result = inventory_captures(tmp_path)
    assert not result['complete']
    assert 'missing manifest' in result['warnings'][0]
    assert (folder/'raw.bin').read_bytes() == b'partially written sample'

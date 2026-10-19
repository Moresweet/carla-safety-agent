import json
import pytest
from carla_safety_agent.capture_references import project_references


def test_real_exported_project_name_reference(tmp_path):
    from carla_safety_agent.scene_store import SceneStore
    from carla_safety_agent.project_bundle import export_bundle
    source = tmp_path/'source'
    store = SceneStore(source/'scenes')
    saved = store.save({'map':'Town04', 'objects':[]}, '基线 capture-example')
    bundles = tmp_path/'bundles'; bundles.mkdir()
    output = bundles/'project.zip'
    export_bundle(store.root, source, [saved['head']['scene_id']], output)
    before = output.read_bytes()
    result = project_references(bundles)
    assert result['complete'] and 'capture-example' in result['references']
    assert result['reference_scan_complete'] and not result['scan_errors']
    assert output.read_bytes() == before


@pytest.mark.parametrize('linked', [False, True])
def test_real_partial_snapshot_retains_references_but_not_cleanup_approval(tmp_path, linked):
    from carla_safety_agent.scene_store import SceneStore
    from carla_safety_agent.project_bundle import export_bundle
    source = tmp_path/'source'
    store = SceneStore(source/'scenes')
    saved = store.save({'map':'Town04', 'objects':[]}, 'capture-partial-only')
    bundles = tmp_path/'bundles'; bundles.mkdir()
    original = tmp_path/'snapshot.zip'
    export_bundle(store.root, source, [saved['head']['scene_id']], original)
    before = original.read_bytes()
    partial = bundles/(('a'*32)+'.partial')
    if linked: partial.symlink_to(original)
    else: partial.write_bytes(before)
    result = project_references(bundles)
    assert not result['complete'] and result['warnings']
    assert ('capture-partial-only' in result['references']) == (not linked)
    assert result['reference_scan_complete'] == (not linked)
    if not linked:
        assert result['references']['capture-partial-only'][0]['bundle'] == partial.name
    assert original.read_bytes() == before and partial.read_bytes() == before


def test_project_json_mentions_protect_sources(tmp_path, monkeypatch):
    path = tmp_path/'project.zip'
    path.write_bytes(b'fixture')
    recovered = 'recovered-'+'a'*32
    monkeypatch.setattr('carla_safety_agent.project_bundle.read_bundle', lambda path: ({}, {
        'scenes/a/one.json':json.dumps({'note':'/recordings/capture-example/index.json',
            'history':['capture-example', recovered], 'capture-key':'annotation'}).encode(),
        'textures/image.png':b'capture-not-a-reference'}))
    result = project_references(tmp_path)
    assert result['complete']
    assert set(result['references']) == {'capture-example', recovered, 'capture-key'}
    assert len(result['references']['capture-example']) == 1
    assert path.read_bytes() == b'fixture'


@pytest.mark.parametrize('case', ['missing', 'link', 'partial', 'invalid', 'limit'])
def test_unreadable_projects_do_not_authorize_cleanup(tmp_path, case):
    root = tmp_path
    if case == 'missing': root = tmp_path/'missing'
    elif case == 'link': (root/'linked.zip').symlink_to('/nonexistent')
    elif case == 'partial': (root/'a.partial').write_bytes(b'partial')
    elif case == 'invalid': (root/'a.zip').write_bytes(b'not zip')
    else:
        (root/'a.partial').write_bytes(b'a')
        (root/'b.partial').write_bytes(b'b')
    result = project_references(root, max_bundles=1)
    assert not result['complete'] and result['warnings']
    assert not result['reference_scan_complete'] and result['scan_errors']


@pytest.mark.parametrize('supported', [True, False])
def test_legacy_references_retained_without_certifying_archive(tmp_path, monkeypatch, supported):
    path = tmp_path/'legacy.zip'; path.write_bytes(b'unchanged')
    def invalid(path):
        raise ValueError('Dependency manifest mismatch')
    def inspect(path):
        if not supported:
            raise ValueError('Not the exact supported legacy asset flags')
        return {}, {'scenes/example.json': b'{"name":"capture-legacy"}'}, {}
    monkeypatch.setattr('carla_safety_agent.project_bundle.read_bundle', invalid)
    monkeypatch.setattr('carla_safety_agent.project_bundle.inspect_legacy_asset_flags', inspect)
    result = project_references(tmp_path)
    assert not result['complete'] and result['warnings']
    assert ('capture-legacy' in result['references']) == supported
    assert result['reference_scan_complete'] == supported
    assert path.read_bytes() == b'unchanged'


def test_checksum_failure_never_uses_legacy_fallback(tmp_path, monkeypatch):
    (tmp_path/'broken.zip').write_bytes(b'broken')
    def invalid(path):
        raise ValueError('Bundle checksum mismatch')
    def forbidden(path):
        pytest.fail('Damaged payload must not use legacy fallback')
    monkeypatch.setattr('carla_safety_agent.project_bundle.read_bundle', invalid)
    monkeypatch.setattr('carla_safety_agent.project_bundle.inspect_legacy_asset_flags', forbidden)
    result = project_references(tmp_path)
    assert not result['complete'] and not result['references']


@pytest.mark.parametrize('fault', [None, 'link', 'broken', 'unknown'])
def test_source_staging_reference_json(tmp_path, fault):
    staging = tmp_path/(('b'*32)+'-sources'); staging.mkdir()
    reference = staging/'reference.json'
    if fault == 'link': reference.symlink_to('/nonexistent')
    elif fault == 'broken': reference.write_bytes(b'{')
    else: reference.write_text('{"note":"capture-staged-source"}')
    if fault == 'unknown': (staging/'z-unknown').write_bytes(b'unknown')
    result = project_references(tmp_path)
    assert not result['complete'] and result['warnings']
    assert ('capture-staged-source' in result['references']) == (fault in (None, 'unknown'))
    assert result['reference_scan_complete'] == (fault is None)
    assert reference.is_symlink() if fault == 'link' else reference.is_file()


def test_source_staging_scan_limit(tmp_path):
    from carla_safety_agent.capture_references import _source_documents
    (tmp_path/'reference.json').write_text('{}')
    with pytest.raises(ValueError, match='scan limit'):
        list(_source_documents(tmp_path, max_entries=0))

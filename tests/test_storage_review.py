import json
import pytest
from carla_safety_agent.storage_review import storage_review
from carla_safety_agent.capture_retention import CaptureRetention


def test_concurrent_review_rejected_and_lock_released_on_error(monkeypatch):
    import importlib
    import threading
    module=importlib.import_module('carla_safety_agent.storage_review')
    entered=threading.Event();release=threading.Event();errors=[]
    def scan(*args):
        entered.set()
        assert release.wait(3)
        raise OSError('injected scan failure')
    monkeypatch.setattr(module,'_storage_review',scan)
    def worker():
        try:module.storage_review('unused','unused')
        except OSError as error:errors.append(str(error))
    thread=threading.Thread(target=worker);thread.start()
    try:
        assert entered.wait(3)
        with pytest.raises(module.StorageReviewBusy):module.storage_review('unused','unused')
    finally:
        release.set();thread.join(3)
    assert not thread.is_alive() and errors==['injected scan failure']
    monkeypatch.setattr(module,'_storage_review',lambda *_:{'complete':True})
    assert module.storage_review('unused','unused')['complete']


def test_review_combines_explicit_and_derived_protection(tmp_path):
    root=tmp_path/'captures';root.mkdir()
    data=tmp_path/'data';(data/'experiment-queues').mkdir(parents=True)
    (data/'project-bundles').mkdir()
    for name,extra in [('source',{}),('copy',{'recovery':{'source_run_id':'source'}})]:
        folder=root/name;folder.mkdir()
        (folder/'manifest.json').write_text(json.dumps({'run_id':name,**extra}))
    CaptureRetention(data,root).set_keep('source',True,'baseline',expected_revision=0)
    result=storage_review(root,data)
    assert result['complete']
    row=next(row for row in result['recordings'] if row['directory']=='source')
    assert row['keep_reason']=='baseline' and len(row['derived_referenced_by'])==1
    assert result['free_bytes']>0


def test_corrupt_protection_refuses_review(tmp_path):
    root=tmp_path/'captures';root.mkdir()
    (tmp_path/'capture-retention.json').write_text('broken')
    with pytest.raises(ValueError):storage_review(root,tmp_path)


@pytest.mark.parametrize('fault', [None, 'modified', 'partial'])
def test_registered_split_references_are_included_without_deletion_approval(tmp_path, fault):
    from carla_safety_agent.dataset_split import verified_split
    from carla_safety_agent.split_registry import register_split
    from pathlib import Path
    root = tmp_path/'captures'; capture = root/'capture-test'; capture.mkdir(parents=True)
    (capture/'manifest.json').write_text(json.dumps({'run_id':capture.name,'status':'saved','frame_count':1}))
    (capture/'index.json').write_text(json.dumps({'frames':[{'frame':1,'timestamp':.05}]}))
    data = tmp_path/'data'; (data/'experiment-queues').mkdir(parents=True); (data/'project-bundles').mkdir()
    source = tmp_path/'split.json'
    source.write_text(json.dumps(verified_split([{'run_id':capture.name,'scene_group':'explicit-group'}], root)))
    registration = register_split(source, data/'dataset-splits', root)
    if fault == 'modified':
        path = Path(registration['path']); value = json.loads(path.read_text()); value['notes'].append('changed'); path.write_text(json.dumps(value))
    elif fault == 'partial':
        (data/'dataset-splits/unfinished.partial').write_text('{')
    before = {p.name:p.read_bytes() for p in capture.iterdir()}
    result = storage_review(root, data)
    assert result['complete'] is (fault is None)
    assert result['registered_split_references']['complete'] is (fault is None)
    assert result['recordings'][0]['split_referenced_by'][0]['path'] == registration['path']
    assert {p.name:p.read_bytes() for p in capture.iterdir()} == before
    if fault: assert result['warnings']


@pytest.mark.parametrize('broken',[False,True])
def test_web_review_includes_real_project_references_and_incomplete_warnings(tmp_path,broken):
    from carla_safety_agent.scene_store import SceneStore
    from carla_safety_agent.project_bundle import export_bundle
    root=tmp_path/'captures';root.mkdir()
    capture=root/'capture-example';capture.mkdir()
    (capture/'manifest.json').write_text(json.dumps({'run_id':capture.name}))
    data=tmp_path/'data';(data/'experiment-queues').mkdir(parents=True)
    bundles=data/'project-bundles';bundles.mkdir()
    store=SceneStore(data/'scenes')
    saved=store.save({'map':'Town04','objects':[]},'Keep capture-example')
    output=bundles/'project.zip'
    export_bundle(store.root,data,[saved['head']['scene_id']],output)
    before=output.read_bytes()
    if broken:(bundles/'unfinished.partial').write_bytes(b'incomplete')
    result=storage_review(root,data)
    assert result['complete'] is (not broken)
    assert result['recordings'][0]['project_referenced_by']
    if broken:assert any('unfinished.partial' in w for w in result['warnings'])
    assert output.read_bytes()==before and capture.is_dir()

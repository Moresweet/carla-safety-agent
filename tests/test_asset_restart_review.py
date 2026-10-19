import hashlib
import json
import pytest
from carla_safety_agent.asset_restart_review import record_review,has_review


def fixture(tmp_path,monkeypatch):
    monkeypatch.setattr('carla_safety_agent.asset_restart_review.observed_process_identity',lambda pid:None)
    job=tmp_path/'abc';job.mkdir();attempt='a'*32
    path=job/f'import-attempt-{attempt}.json'
    row=dict(schema_version='carla-asset-import/1',job_id='abc',attempt_id=attempt,
             report_path=str(path),state='needs_attention',started_at=1,ended_at=2,
             owner={'pid':123,'start_ticks':'7'},
             error='Generated asset ID already registered; choose a new name')
    path.write_text(json.dumps(row))
    return path,attempt


def test_review_preserves_original_and_invalidates_on_change(tmp_path,monkeypatch):
    path,attempt=fixture(tmp_path,monkeypatch);before=path.read_bytes()
    record_review(tmp_path,'abc',attempt,hashlib.sha256(before).hexdigest())
    assert has_review(tmp_path,'abc',attempt)
    assert path.read_bytes()==before
    path.write_bytes(before+b' ')
    with pytest.raises(ValueError):has_review(tmp_path,'abc',attempt)


@pytest.mark.parametrize('reason',['alive','artifact','hash'])
def test_review_rejects_uncertain_evidence(tmp_path,monkeypatch,reason):
    path,attempt=fixture(tmp_path,monkeypatch)
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    if reason=='alive':monkeypatch.setattr('carla_safety_agent.asset_restart_review.observed_process_identity',lambda pid:{'pid':123,'start_ticks':'7'})
    if reason=='artifact':(path.parent/f'unreal-request-{attempt}.json').write_text('{}')
    if reason=='hash':digest='0'*64
    with pytest.raises(ValueError):record_review(tmp_path,'abc',attempt,digest)
    assert not list(path.parent.glob('restart-review-*'))


@pytest.mark.parametrize('value', [None, [], 'text', 1, True])
def test_non_object_journal_refused(tmp_path, monkeypatch, value):
    path, attempt = fixture(tmp_path, monkeypatch)
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match='must be an object'):
        record_review(tmp_path, 'abc', attempt, '0'*64)
    assert not list(path.parent.glob('restart-review-*'))


@pytest.mark.parametrize('job,attempt', [('../outside','a'*32), ('abc','../outside'),
    (None,'a'*32), ('abc',None)])
def test_review_identity_checked_even_without_receipt(tmp_path, job, attempt):
    with pytest.raises(ValueError, match='identity'):
        has_review(tmp_path, job, attempt)


def test_linked_runtime_and_dangling_receipt_refused(tmp_path, monkeypatch):
    root = tmp_path/'real'
    root.mkdir()
    path, attempt = fixture(root, monkeypatch)
    link = tmp_path/'linked'
    link.symlink_to(root, target_is_directory=True)
    with pytest.raises(ValueError, match='Linked'):
        has_review(link, 'abc', attempt)
    (path.parent/f'restart-review-{attempt}.json').symlink_to(tmp_path/'missing')
    with pytest.raises(ValueError, match='Linked'):
        has_review(root, 'abc', attempt)


@pytest.mark.parametrize('kind', ['fifo', 'oversized', 'symlink'])
def test_non_regular_or_unbounded_journal_refused(tmp_path, monkeypatch, kind):
    import os
    path, attempt = fixture(tmp_path, monkeypatch)
    path.unlink()
    if kind == 'fifo':
        os.mkfifo(path)
    elif kind == 'oversized':
        path.write_bytes(b' '*65537)
    else:
        target = tmp_path/'target.json'
        target.write_text('{}')
        path.symlink_to(target)
    with pytest.raises((ValueError, OSError)):
        record_review(tmp_path, 'abc', attempt, '0'*64)
    assert not list(path.parent.glob('restart-review-*'))

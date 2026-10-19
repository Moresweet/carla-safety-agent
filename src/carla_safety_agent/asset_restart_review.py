"""Explicit legacy pre-launch rejection review, never an asset success receipt."""
import hashlib
import json
import math
import os
import stat
from pathlib import Path

from .owned_resources import durable_write
from .session import observed_process_identity


def review_job(runtime, job_id, attempt_id):
    runtime = Path(runtime)
    if (not isinstance(job_id, str) or not job_id.isascii() or not job_id.isalnum()
            or len(job_id) > 64 or not isinstance(attempt_id, str)
            or len(attempt_id) != 32 or any(c not in '0123456789abcdef' for c in attempt_id)):
        raise ValueError('Invalid asset review identity')
    job = runtime / job_id
    if runtime.is_symlink() or job.is_symlink():
        raise ValueError('Linked asset review directory')
    return job


def read_record(path):
    # No-follow and nonblocking also reject links/FIFOs without reading them.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        metadata = os.fstat(stream.fileno())
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 65536:
            raise ValueError('Invalid asset review file')
        raw = stream.read(65537)
    if len(raw) > 65536:
        raise ValueError('Oversized asset review file')
    row = json.loads(raw)
    if not isinstance(row, dict):
        raise ValueError('Asset review record must be an object')
    return raw, row


def evidence(runtime, job_id, attempt_id, *, reviewed=False):
    job = review_job(runtime, job_id, attempt_id)
    path = job / f'import-attempt-{attempt_id}.json'
    raw, row = read_record(path)
    if (row.get('schema_version') != 'carla-asset-import/1'
            or row.get('job_id') != job_id or row.get('attempt_id') != attempt_id
            or row.get('report_path') != str(path) or row.get('state') != 'needs_attention'
            or row.get('error') != 'Generated asset ID already registered; choose a new name'
            or any(k in row for k in ('worker_state','destination','request_path','result_path','asset_name'))):
        raise ValueError('Not a reviewable legacy pre-launch rejection')
    started, ended = row.get('started_at'), row.get('ended_at')
    if (type(started) not in (int,float) or type(ended) not in (int,float)
            or not math.isfinite(started) or not math.isfinite(ended) or ended < started):
        raise ValueError('Missing terminal review evidence')
    owner = row.get('owner')
    if (not isinstance(owner, dict) or set(owner) != {'pid','start_ticks'}
            or type(owner['pid']) is not int or owner['pid'] <= 0
            or not isinstance(owner['start_ticks'], str) or not owner['start_ticks'].isdigit()):
        raise ValueError('Invalid historical coordinator identity')
    if observed_process_identity(owner['pid']) == owner:
        raise ValueError('Historical coordinator is still alive')
    allowed = {path}
    if reviewed:
        allowed.add(job / ('restart-review-' + attempt_id + '.json'))
    if set(job.glob('*'+attempt_id+'*')) != allowed:
        raise ValueError('Attempt has additional native artifacts; manual inspection required')
    return hashlib.sha256(raw).hexdigest(), path


def record_review(runtime, job_id, attempt_id, expected_sha256):
    digest, path = evidence(runtime, job_id, attempt_id)
    if digest != expected_sha256:
        raise ValueError('Asset journal changed after review')
    destination = path.parent / ('restart-review-' + attempt_id + '.json')
    receipt = {'schema_version':'asset-restart-review/1','job_id':job_id,'attempt_id':attempt_id,
               'journal_sha256':digest,'decision':'legacy_prelaunch_rejection',
               'asset_success':False,'automatic_retry':False}
    durable_write(destination, receipt, exclusive=True)
    return receipt


def has_review(runtime, job_id, attempt_id):
    job = review_job(runtime, job_id, attempt_id)
    review = job / ('restart-review-' + attempt_id + '.json')
    if review.is_symlink():
        raise ValueError('Linked asset restart review')
    if not review.exists():
        return False
    # The review is the only allowed extra attempt-scoped file.
    _, value = read_record(review)
    digest, path = evidence(runtime, job_id, attempt_id, reviewed=True)
    if (value != {'schema_version':'asset-restart-review/1','job_id':job_id,'attempt_id':attempt_id,
                  'journal_sha256':digest,
                  'decision':'legacy_prelaunch_rejection','asset_success':False,'automatic_retry':False}
            or path.is_symlink() or review.parent.is_symlink()
            or set(review.parent.glob('*'+attempt_id+'*')) != {path,review}):
        raise ValueError('Asset restart review no longer matches journal/artifacts')
    return True

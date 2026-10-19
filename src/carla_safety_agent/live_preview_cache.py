"""Bounded live preview retention; never operates on saved recordings."""
import json
import math
import os
import stat
import time
from pathlib import Path

CAMERAS = ('CAM_FRONT', 'CAM_FRONT_LEFT', 'CAM_FRONT_RIGHT', 'CAM_BACK', 'CAM_BACK_LEFT', 'CAM_BACK_RIGHT')
FILES = {name+'.jpg' for name in CAMERAS} | {
    'DEPTH_'+name+extension for name in CAMERAS for extension in ('.jpg', '.npy')
} | {'BEV_POINTS.jpg', 'BEV_RGB.jpg', 'LIDAR.npy', 'bev.jpg', 'rgb_back.jpg',
     'rgb_front.jpg', 'rgb_left.jpg', 'rgb_right.jpg', 'topdown.jpg'}


def read_preview_manifest(path):
    """Bounded no-follow read; a FIFO must never stall the capture tick."""
    limit=8*1024**2
    descriptor=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(descriptor,'rb') as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size>limit:
            raise ValueError('Invalid preview manifest type or size')
        raw=stream.read(limit+1)
    if len(raw)>limit:
        raise ValueError('Preview manifest exceeds size limit')
    return raw


def prune_previews(live, *, keep=6, grace_seconds=60, now=None):
    """Caller must hold capture_write_lock(live) throughout publishing/pruning.

    Only known flat preview generations qualify. Unknown files are preserved.
    Retain the manifest's current generation, newest others, and reader grace.
    This is not safe against non-cooperating external filesystem mutations.
    """
    live = Path(live)
    if (type(keep) is not int or keep < 1
            or type(grace_seconds) not in (int, float)
            or not math.isfinite(grace_seconds) or grace_seconds < 0
            or (now is not None and (type(now) not in (int, float)
                or not math.isfinite(now) or now < 0))):
        raise ValueError('Invalid preview retention')
    frames, latest = live/'frames', live/'latest.json'
    if live.is_symlink() or frames.is_symlink() or latest.is_symlink():
        raise ValueError('Linked preview cache')
    original = read_preview_manifest(latest)
    def unique_pairs(pairs):
        result={}
        for key,value in pairs:
            if key in result:
                raise ValueError('Duplicate preview manifest field')
            result[key]=value
        return result
    def invalid_constant(value):
        raise ValueError('Non-finite preview manifest value: '+value)
    metadata = json.loads(original, object_pairs_hook=unique_pairs, parse_constant=invalid_constant)
    if not isinstance(metadata, dict):
        raise ValueError('Invalid preview manifest')
    current = metadata.get('generation')
    if (not isinstance(current, str) or not current.startswith('frames/')
            or not current[7:].isascii() or not current[7:].isdigit()
            or not (live/current).is_dir() or (live/current).is_symlink()):
        raise ValueError('Invalid current preview generation')
    now = time.time() if now is None else now
    candidates, skipped = [], []
    for folder in frames.iterdir():
        if folder.is_symlink() or not folder.is_dir() or not folder.name.isascii() or not folder.name.isdigit():
            skipped.append(folder.name)
            continue
        entries = []
        for path in folder.iterdir():
            info = path.lstat()
            if path.name not in FILES or not stat.S_ISREG(info.st_mode):
                break
            entries.append((path, info))
        else:
            newest = max([folder.stat().st_mtime] + [info.st_mtime for _, info in entries])
            candidates.append((folder, entries, newest))
            continue
        skipped.append(folder.name)
    protected = {current[7:]}
    for folder, _, _ in sorted(candidates, key=lambda row: row[2], reverse=True):
        if len(protected) >= keep:
            break
        protected.add(folder.name)
    removed, released = [], 0
    for folder, entries, newest in candidates:
        if folder.name in protected or now-newest < grace_seconds:
            continue
        if read_preview_manifest(latest) != original:
            raise ValueError('Preview publication changed during cleanup')
        # Recheck every entry before touching a generation.
        if set(folder.iterdir()) != {path for path, _ in entries}:
            raise ValueError('Preview generation changed during cleanup')
        for path, old in entries:
            fresh = path.lstat()
            if (fresh.st_ino, fresh.st_dev, fresh.st_size, fresh.st_mtime_ns, fresh.st_mode) != (
                    old.st_ino, old.st_dev, old.st_size, old.st_mtime_ns, old.st_mode):
                raise ValueError('Preview file changed during cleanup')
        for path, info in entries:
            path.unlink()
            released += info.st_blocks*512
        folder.rmdir()
        removed.append(folder.name)
    return {'removed_generations': removed, 'removed_allocated_bytes': released,
            'protected': sorted(protected), 'skipped': sorted(skipped),
            'raw_recoverable': False}

"""Verified recording archive copies; never remove the source recording."""
import hashlib
import json
import os
import re
import stat
import tempfile
from pathlib import Path
import shutil
import zipfile
from .capture_recovery import inventory
from .scene_store import read_json, identifier


def restore_capture_archive(archive_path, destination_parent):
    """Restore to an isolated directory; never merge with the live dataset root."""
    receipt=verify_capture_archive(archive_path)
    parent=Path(destination_parent)
    if parent.is_symlink() or not parent.is_dir():raise ValueError('Restore parent must be a real directory')
    if shutil.disk_usage(parent).free<receipt['source_bytes']+1024**3:
        raise ValueError('Restore requires expanded size plus 1 GiB free')
    stage=Path(tempfile.mkdtemp(prefix='capture-restore-',dir=parent))
    source=stage/receipt['source_run_id'];source.mkdir()
    # On failure leave an isolated partial directory with no success receipt.
    with zipfile.ZipFile(archive_path) as archive:
        for name,expected in receipt['files'].items():
            target=source/name
            target.parent.mkdir(parents=True,exist_ok=True)
            digest=hashlib.sha256();size=0
            with archive.open(name) as stream,target.open('xb') as output:
                for chunk in iter(lambda:stream.read(1024**2),b''):
                    size+=len(chunk)
                    if size>expected['bytes']:raise ValueError('Archive changed during restoration')
                    if shutil.disk_usage(parent).free < len(chunk)+1024**3:
                        raise ValueError('Restore disk reserve reached; isolated partial copy retained')
                    output.write(chunk);digest.update(chunk)
                output.flush();os.fsync(output.fileno())
            if size!=expected['bytes'] or digest.hexdigest()!=expected['sha256']:
                raise ValueError('Restored content mismatch')
    if inventory(source)[0]!=receipt['files']:raise ValueError('Restored inventory mismatch')
    result={'schema_version':'carla-capture-restore/1','verified':True,
            'directory':str(source.absolute()),'source_run_id':receipt['source_run_id'],
            'files':len(receipt['files']),'bytes':receipt['source_bytes'],
            'registered_for_replay':False,'scope':'Byte restoration only; original recording status retained'}
    with (stage/'restore-receipt.json').open('x') as stream:json.dump(result,stream,indent=2)
    return result


def verify_capture_archive(path):
    """Validate a standalone archive without extracting files or needing its source."""
    path=Path(path)
    if path.is_symlink() or not path.is_file():raise ValueError('Archive must be a regular file')
    with zipfile.ZipFile(path) as archive:
        entries=archive.infolist();names=[entry.filename for entry in entries]
        if len(names)>300001 or len(names)!=len(set(names)) or 'capture-archive.json' not in names:
            raise ValueError('Invalid archive entry list')
        if sum(entry.file_size for entry in entries)>20*1024**3+64*1024**2:
            raise ValueError('Archive expansion limit exceeded')
        for entry in entries:
            name=entry.filename
            if not name or name.startswith('/') or '\\' in name or any(part in ('','..','.') for part in name.split('/')) or ':' in name:
                raise ValueError('Unsafe archive path')
            mode=entry.external_attr>>16
            if stat.S_IFMT(mode) not in (0,stat.S_IFREG):raise ValueError('Archive entry is not a regular file')
        if archive.getinfo('capture-archive.json').file_size>64*1024**2:raise ValueError('Archive receipt too large')
        receipt=json.loads(archive.read('capture-archive.json'))
        if not isinstance(receipt,dict) or receipt.get('schema_version')!='carla-capture-archive/1':raise ValueError('Unsupported archive schema')
        identifier(receipt.get('source_run_id'))
        files=receipt.get('files')
        if not isinstance(files,dict) or set(files)!=set(names)-{'capture-archive.json'} or 'manifest.json' not in files:
            raise ValueError('Archive file inventory mismatch')
        total=0
        for name,expected in files.items():
            if not isinstance(expected,dict) or type(expected.get('bytes')) is not int or expected['bytes']<0 or not isinstance(expected.get('sha256'),str) or not re.fullmatch('[a-f0-9]{64}',expected['sha256']):
                raise ValueError('Invalid file evidence')
            if archive.getinfo(name).file_size!=expected['bytes']:raise ValueError('Archive size mismatch')
            digest=hashlib.sha256()
            with archive.open(name) as stream:
                for chunk in iter(lambda:stream.read(1024**2),b''):digest.update(chunk)
            if digest.hexdigest()!=expected['sha256']:raise ValueError('Archive checksum mismatch')
            total+=expected['bytes']
        if total>20*1024**3 or type(receipt.get('source_bytes')) is not int or receipt['source_bytes']!=total:raise ValueError('Archive total mismatch or limit exceeded')
        if archive.getinfo('manifest.json').file_size>8*1024**2:raise ValueError('Recording manifest too large')
        manifest=json.loads(archive.read('manifest.json'))
        if not isinstance(manifest,dict) or manifest.get('run_id')!=receipt['source_run_id']:raise ValueError('Archived recording identity mismatch')
    return receipt


def archive_capture(source, output, require_inactive):
    source, output = Path(source), Path(output)
    if output.exists() or output.is_symlink():raise ValueError('Archive output already exists')
    if source.is_symlink() or not source.is_dir():raise ValueError('Invalid recording directory')
    if output.resolve().is_relative_to(source.resolve()):raise ValueError('Archive cannot be inside source')
    require_inactive()
    manifest = read_json(source/'manifest.json',max_bytes=8*1024**2)
    if not isinstance(manifest,dict) or manifest.get('run_id') != source.name:
        raise ValueError('Recording identity mismatch')
    before,total = inventory(source)
    if 'capture-archive.json' in before:raise ValueError('Reserved archive entry exists')
    if shutil.disk_usage(output.parent).free < total+1024**3:
        raise ValueError('Archive requires source size plus 1 GiB available space')
    # A failed copy remains visibly partial for inspection, never a finalized ZIP.
    partial = output.with_name(output.name+'.partial')
    if partial.exists() or partial.is_symlink():raise ValueError('Partial archive already exists')
    receipt={'schema_version':'carla-capture-archive/1','source_run_id':source.name,
             'files':before,'source_bytes':total,
             'scope':'Byte-preserving backup only; not sensor quality or successful execution certification'}
    with partial.open('xb') as stream:
        with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED,compresslevel=1) as archive:
            for name in sorted(before):
                # A long export can outlive the initial free-space observation.
                # Reserve uncompressed file size plus conservative ZIP overhead.
                needed=before[name]['bytes']+before[name]['bytes']//1000+65536
                if shutil.disk_usage(output.parent).free < needed+1024**3:
                    raise ValueError('Archive disk reserve reached; partial copy retained')
                archive.write(source/name,name)
            archive.writestr('capture-archive.json',json.dumps(receipt,ensure_ascii=False))
        stream.flush()
        os.fsync(stream.fileno())
    with zipfile.ZipFile(partial) as archive:
        if set(archive.namelist()) != set(before)|{'capture-archive.json'}:
            raise ValueError('Archive entries mismatch')
        for name,expected in before.items():
            digest=hashlib.sha256();size=0
            with archive.open(name) as stream:
                for chunk in iter(lambda:stream.read(1024**2),b''):
                    digest.update(chunk);size+=len(chunk)
            if {'sha256':digest.hexdigest(),'bytes':size} != expected:
                raise ValueError(f'Archive content mismatch: {name}')
    require_inactive()
    if inventory(source)[0] != before:raise ValueError('Source changed during archive; partial copy retained')
    # Hard-link publication refuses an existing destination, unlike rename.
    os.link(partial,output)
    partial.unlink()
    return {**receipt,'archive':str(output.absolute()),'archive_bytes':output.stat().st_size,
            'verified':True,'source_removed':False}

"""Explicit, idempotent background archive jobs; source recordings are preserved."""
from pathlib import Path
import threading
import re
import hashlib
import os
import stat
from .scene_store import atomic,read_json,identifier
from .capture_recovery import require_inactive_execution
from .capture_archive import archive_capture


class ArchiveService:
    def __init__(self,datasets,reports,data_root):
        self.datasets,self.reports,self.data_root=map(Path,(datasets,reports,data_root))
        self.lock=threading.RLock();self.active=None

    def _path(self,request_id):
        if not isinstance(request_id,str) or not re.fullmatch('[a-f0-9]{32}',request_id):
            raise ValueError('Invalid archive request ID')
        return self.reports/(request_id+'.json')

    def status(self,request_id):
        with self.lock:
            row=read_json(self._path(request_id),max_bytes=1024**2)
            if not isinstance(row,dict) or row.get('request_id')!=request_id:raise ValueError('Archive report identity mismatch')
            if row['state']=='running' and self.active!=request_id:
                return {**row,'state':'needs_attention','error':'Archive worker interrupted; inspect retained output. No automatic retry.'}
            return row

    def start(self,data):
        if not isinstance(data,dict) or set(data)!={'run_id','request_id','confirmed'} or data['confirmed'] is not True:
            raise ValueError('Archive requires run_id, request_id and explicit confirmation')
        request_id=data['request_id'];path=self._path(request_id);run_id=identifier(data['run_id'])
        with self.lock:
            if path.exists() or path.is_symlink():
                row=self.status(request_id)
                if row['source_run_id']!=run_id:raise ValueError('Archive request belongs to another recording')
                return row
            if self.active is not None:raise ValueError('Another archive job is running')
            source=self.datasets/run_id
            if self.datasets.is_symlink() or source.is_symlink():raise ValueError('Linked recording root refused')
            manifest=read_json(source/'manifest.json',max_bytes=8*1024**2)
            if not isinstance(manifest,dict) or manifest.get('run_id')!=run_id:raise ValueError('Source identity mismatch')
            execution=identifier(manifest.get('execution_id'))
            require_inactive_execution(self.data_root,execution)
            self.reports.mkdir(parents=True,exist_ok=True)
            row={'request_id':request_id,'source_run_id':run_id,'state':'running',
                 'source_manifest_sha256':hashlib.sha256((source/'manifest.json').read_bytes()).hexdigest(),
                 'source_removed':False}
            atomic(path,row);self.active=request_id
            try:threading.Thread(target=self._run,args=(row,source,execution),daemon=True).start()
            except Exception as exc:
                self.active=None;atomic(path,{**row,'state':'failed','error':str(exc)});raise
            return row

    def _run(self,row,source,execution):
        try:
            if hashlib.sha256((source/'manifest.json').read_bytes()).hexdigest()!=row['source_manifest_sha256']:
                raise ValueError('Source manifest changed after confirmation')
            output=self.reports/(row['request_id']+'.zip')
            result=archive_capture(source,output,lambda:require_inactive_execution(self.data_root,execution))
            digest=hashlib.sha256()
            with output.open('rb') as stream:
                for chunk in iter(lambda:stream.read(1024**2),b''):digest.update(chunk)
            row={**row,'state':'archived','archive_bytes':result['archive_bytes'],
                 'archive_sha256':digest.hexdigest(),
                 'source_bytes':result['source_bytes'],'archive_file':output.name,
                 'note':'Verified byte archive; source preserved, not deletion approval'}
        except Exception as exc:row={**row,'state':'failed','error':str(exc)}
        finally:
            with self.lock:
                try:atomic(self._path(row['request_id']),row)
                finally:self.active=None

    def open_download(self,request_id):
        row=self.status(request_id)
        if row['state']!='archived':raise ValueError('Archive is not ready')
        # Use the validated ID, never a report-provided path. Validate and serve
        # the same descriptor so path replacement cannot swap the download.
        path=self.reports/(request_id+'.zip')
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        stream=os.fdopen(fd,'rb')
        try:
            info=os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size!=row.get('archive_bytes'):
                raise ValueError('Archive size or file type changed')
            digest=hashlib.sha256()
            for chunk in iter(lambda:stream.read(1024**2),b''):digest.update(chunk)
            if digest.hexdigest()!=row.get('archive_sha256'):raise ValueError('Archive checksum changed')
            stream.seek(0)
            return stream
        except BaseException:
            stream.close();raise

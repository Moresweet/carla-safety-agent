"""Confirmed native asset registration produces a new package, never a world restore."""
import fcntl
import hashlib
import json
from pathlib import Path
import re
import threading
import uuid

from .bundle_registration import register_bundle
from .owned_resources import durable_write
from .project_bundle import read_bundle


def native_import_busy(project):
    path=Path(project)/'.runtime/blender-assets/import.lock'
    if path.is_symlink():raise ValueError('Redirected native import lock')
    try:stream=path.open('rb')
    except FileNotFoundError:return False
    with stream:
        try:fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return True
        return False


class BundleRegistrationService:
    def __init__(self,workbench,require_idle):
        self.workbench=workbench;self.require_idle=require_idle
        self.root=workbench.project/'.runtime/bundle-registration'
        self.lock=threading.RLock();self.active=None

    def _path(self,request_id):
        if not isinstance(request_id,str) or not re.fullmatch('[a-f0-9]{32}',request_id):raise ValueError('Invalid registration request ID')
        return self.root/(request_id+'.json')

    def status(self,request_id):
        with self.lock:
            row=json.loads(self._path(request_id).read_text())
            if row.get('request_id')!=request_id:raise ValueError('Registration report identity mismatch')
            if row['state']=='running' and self.active!=request_id:
                row={**row,'state':'needs_attention','error':'Registration worker interrupted; retained native assets require inspection; no automatic retry'}
            return row

    def start(self,data):
        if not isinstance(data,dict) or set(data)!={'bundle_id','request_id','confirmed'} or data['confirmed'] is not True:
            raise ValueError('Explicit confirmation and package/request IDs are required')
        path=self._path(data['request_id'])
        with self.lock:
            if path.exists():
                row=self.status(data['request_id'])
                if row['bundle_id']!=data['bundle_id']:raise ValueError('Registration request belongs to another package')
                return row
            if self.active is not None:raise ValueError('Another bundle registration is running')
            self.require_idle()
            if native_import_busy(self.workbench.project):raise ValueError('A native import still holds the asset lock')
            source=self.workbench.path(data['bundle_id'])
            manifest,_=read_bundle(source)
            count=len(manifest['dependencies'].get('generated_asset_sources',{}))
            if not 1<=count<=8:raise ValueError('GUI registration requires 1..8 bundled source assets; use the CLI for larger packages')
            output_id=uuid.uuid4().hex
            row={'request_id':data['request_id'],'bundle_id':data['bundle_id'],'state':'running',
                 'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'output_bundle_id':output_id,
                 'source_asset_count':count,'live_world_modified':False,'restored':False}
            durable_write(path,row,exclusive=True);self.active=data['request_id']
            try:threading.Thread(target=self._run,args=(row,source),daemon=True).start()
            except Exception as exc:
                self.active=None;durable_write(path,{**row,'state':'needs_attention','error':str(exc)});raise
            return row

    def _run(self,row,source):
        try:
            self.require_idle()
            if hashlib.sha256(source.read_bytes()).hexdigest()!=row['source_sha256']:raise ValueError('Package changed after confirmation')
            result=register_bundle(source,self.workbench.project,self.workbench.path(row['output_bundle_id']),execute=True)
            row={**row,'state':'registered','registration':result}
        except Exception as exc:row={**row,'state':'needs_attention','error':str(exc)}
        finally:
            with self.lock:
                try:durable_write(self._path(row['request_id']),row)
                finally:self.active=None

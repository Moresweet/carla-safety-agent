"""One asynchronous, explicitly confirmed recovery copy at a time."""
import hashlib
import json
from pathlib import Path
import re
import threading

from .capture_recovery import recover_capture,require_inactive_execution
from .scene_store import atomic
from .capture_quota import publish_capture


class RecoveryService:
    def __init__(self,datasets,reports,data_root,validator,python):
        self.datasets,self.reports,self.data_root=map(Path,(datasets,reports,data_root))
        self.validator,self.python=validator,python
        self.lock=threading.RLock();self.active=None

    def _path(self,request_id):
        if not isinstance(request_id,str) or not re.fullmatch('[a-f0-9]{32}',request_id):
            raise ValueError('Expected a recovery request ID')
        return self.reports/(request_id+'.json')

    def status(self,request_id):
        with self.lock:
            row=json.loads(self._path(request_id).read_text())
            if row.get('request_id')!=request_id:raise ValueError('Recovery report identity mismatch')
            if row['state']=='running' and self.active!=request_id:
                row={**row,'state':'needs_attention','error':'Recovery worker interrupted; inspect retained copies. No automatic retry.'}
            candidate=row.get('candidate_run_id')
            if candidate is not None:
                if not isinstance(candidate,str) or not re.fullmatch('recovered-[a-f0-9]{32}',candidate):
                    raise ValueError('Invalid recovery candidate identity')
                staged=self.reports/'copies'/request_id/candidate
                destination=self.datasets/candidate
                def present(path,root):
                    if root.is_symlink() or any(part.is_symlink() for part in (path,*path.parents) if part==root or root in part.parents):
                        raise ValueError('Linked recovery inspection path')
                    return path.is_dir()
                row={**row,'candidate_presence':{
                    'staged':present(staged,self.reports),
                    'published':present(destination,self.datasets),
                    'raw_data_verified':False,
                    'note':'Directory presence only; not a new audit or recovery approval'}}
            return row

    def start(self,data):
        if not isinstance(data,dict) or set(data)!={'run_id','request_id','confirmed'} or data['confirmed'] is not True:
            raise ValueError('Recovery requires run_id, request_id and explicit confirmation')
        request_id=data['request_id'];report_path=self._path(request_id);run_id=data['run_id']
        if not isinstance(run_id,str) or not re.fullmatch('capture-[A-Za-z0-9-]+',run_id):raise ValueError('Expected an original capture ID')
        with self.lock:
            if report_path.exists():
                row=self.status(request_id)
                if row['source_run_id']!=run_id:raise ValueError('Recovery request already belongs to another source')
                return row
            if self.active is not None:raise ValueError('Another capture recovery is running')
            source=self.datasets/run_id
            if source.is_symlink() or source.resolve().parent!=self.datasets.resolve():raise ValueError('Invalid recovery source')
            if (source/'manifest.json').is_symlink() or (source/'manifest.json').stat().st_size>8*1024*1024:
                raise ValueError('Invalid source manifest path or size')
            payload=(source/'manifest.json').read_bytes();manifest=json.loads(payload)
            if manifest.get('run_id')!=run_id:raise ValueError('Source capture identity mismatch')
            if manifest.get('status') not in ('recording','saved_cleanup_error','saved_capture_error'):raise ValueError('Source is not interrupted or failed')
            require_inactive_execution(self.data_root,manifest['execution_id'])
            self.reports.mkdir(parents=True,exist_ok=True)
            row={'request_id':request_id,'source_run_id':run_id,'state':'running',
                 'source_manifest_sha256':hashlib.sha256(payload).hexdigest(),'source_modified':False}
            atomic(report_path,row);self.active=request_id
            try:threading.Thread(target=self._run,args=(row,source,manifest['execution_id']),daemon=True).start()
            except Exception as exc:
                self.active=None;atomic(report_path,{**row,'state':'failed','error':str(exc)});raise
            return row

    def _run(self,row,source,execution_id):
        request_id=row['request_id']
        try:
            def inactive():require_inactive_execution(self.data_root,execution_id)
            if hashlib.sha256((source/'manifest.json').read_bytes()).hexdigest()!=row['source_manifest_sha256']:
                raise ValueError('Source changed after confirmation')
            # Durable ownership before copying, so interrupted work is locatable.
            staging=self.reports/'copies'/request_id
            row={**row,'phase':'copying','staging_directory':str(staging)}
            atomic(self._path(request_id),row)
            staging.mkdir(parents=True,exist_ok=False)
            output=recover_capture(source,staging,self.validator,self.python,inactive)
            inactive()
            destination=self.datasets/output.name
            if destination.exists():raise ValueError('Recovery destination exists; refusing overwrite')
            row={**row,'phase':'publishing','candidate_run_id':output.name}
            atomic(self._path(request_id),row)
            publish_capture(output,self.datasets)
            row={**row,'state':'recovered','phase':'published','recovered_run_id':destination.name,
                 'note':'Recovered subset, not a successful full recording; original preserved'}
        except Exception as exc:row={**row,'state':'failed','error':str(exc)}
        finally:
            with self.lock:
                try:atomic(self._path(request_id),row)
                finally:self.active=None

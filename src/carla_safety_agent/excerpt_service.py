"""Explicit, idempotent background creation of audited replay excerpts."""
from pathlib import Path
import re
import threading

from .capture_excerpt import create_excerpt,file_evidence,select_window
from .capture_recovery import require_inactive_execution
from .scene_store import atomic,read_json
from .capture_quota import publish_capture


class ExcerptService:
    def __init__(self,datasets,reports,data_root,validator,python):
        self.datasets,self.reports,self.data_root=map(Path,(datasets,reports,data_root))
        self.validator,self.python=validator,python
        self.lock=threading.RLock();self.active=None

    def _path(self,request_id):
        if not isinstance(request_id,str) or not re.fullmatch('[a-f0-9]{32}',request_id):raise ValueError('Invalid excerpt request ID')
        return self.reports/(request_id+'.json')

    def status(self,request_id):
        with self.lock:
            row=read_json(self._path(request_id))
            if row.get('request_id')!=request_id:raise ValueError('Excerpt job identity mismatch')
            if row['state']=='running' and self.active!=request_id:
                row={**row,'state':'needs_attention','error':'Excerpt worker interrupted; retained copies require inspection; no automatic retry'}
            return row

    def start(self,data):
        required={'run_id','request_id','frame','before_s','after_s','confirmed'}
        if not isinstance(data,dict) or set(data)!=required or data['confirmed'] is not True:
            raise ValueError('Excerpt requires an exact selection and explicit confirmation')
        request_id=data['request_id'];path=self._path(request_id);run_id=data['run_id']
        if not isinstance(run_id,str) or not re.fullmatch('(capture|recovered)-[A-Za-z0-9-]+',run_id):
            raise ValueError('Select an original finalized capture or recovered copy')
        source=self.datasets/run_id
        if source.is_symlink() or source.resolve().parent!=self.datasets.resolve():raise ValueError('Invalid excerpt source')
        manifest=read_json(source/'manifest.json',max_bytes=8*1024**2)
        if manifest.get('run_id')!=run_id or manifest.get('status') not in ('saved','saved_limit','saved_recovered'):
            raise ValueError('Capture is not finalized')
        _,window=select_window(read_json(source/'index.json')['frames'],manifest,data['frame'],data['before_s'],data['after_s'])
        selection={key:data[key] for key in ('run_id','frame','before_s','after_s')}
        with self.lock:
            if path.exists():
                row=self.status(request_id)
                if row.get('selection')!=selection:raise ValueError('Excerpt request belongs to another selection')
                return row
            if self.active is not None:raise ValueError('Another excerpt is being archived')
            require_inactive_execution(self.data_root,manifest['execution_id'])
            self.reports.mkdir(parents=True,exist_ok=True)
            row={'request_id':request_id,'state':'running','selection':selection,'window':window,
                'source_run_id':run_id,'source_manifest':file_evidence(source,'manifest.json'),
                'source_index':file_evidence(source,'index.json')}
            atomic(path,row);self.active=request_id
            try:threading.Thread(target=self._run,args=(row,source,manifest['execution_id']),daemon=True).start()
            except Exception as exc:
                self.active=None;atomic(path,{**row,'state':'failed','error':str(exc)});raise
            return row

    def _run(self,row,source,execution_id):
        request_id=row['request_id'];selection=row['selection']
        try:
            def inactive():require_inactive_execution(self.data_root,execution_id)
            if file_evidence(source,'manifest.json')!=row['source_manifest'] or file_evidence(source,'index.json')!=row['source_index']:
                raise ValueError('Source changed after excerpt confirmation')
            dataset,bundle,report=create_excerpt(source,self.reports/request_id,selection['frame'],
                selection['before_s'],selection['after_s'],self.validator,self.python,inactive)
            inactive()
            destination=self.datasets/dataset.name
            if destination.exists() or destination.is_symlink():raise ValueError('Excerpt destination already exists')
            archive=file_evidence(bundle.parent,bundle.name,max_bytes=8*1024**3)
            publish_capture(dataset,self.datasets)
            row={**row,'state':'ready','excerpt_run_id':destination.name,'archive':archive,
                'window':report['window'],'raw_data_verified':True,'source_modified':False,
                'note':'Audited excerpt, not a complete recording or automatically approved training data'}
        except Exception as exc:row={**row,'state':'failed','error':str(exc)}
        finally:
            with self.lock:
                try:atomic(self._path(request_id),row)
                finally:self.active=None

    def download(self,request_id):
        row=self.status(request_id)
        if row['state']!='ready':raise ValueError('Excerpt archive is not ready')
        path=self.reports/request_id/'excerpt.zip'
        if file_evidence(path.parent,path.name,max_bytes=8*1024**3)!=row['archive']:
            raise ValueError('Excerpt archive changed after validation')
        return path

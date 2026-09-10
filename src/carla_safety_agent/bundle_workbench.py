"""Local UI packaging; isolated imports never install into the active project."""
import io
import json
import os
from pathlib import Path
import threading
import uuid
from contextlib import contextmanager

from .project_bundle import export_bundle, import_bundle, read_bundle
from .scene_store import identifier

UPLOAD_LIMIT = 16 * 1024 * 1024


class BundleWorkbench:
    def __init__(self, project):
        self.project = Path(project).resolve()
        self.root = self.project/'data/project-bundles'
        self.lock = threading.Lock()

    @contextmanager
    def operation(self):
        if not self.lock.acquire(blocking=False):
            raise ValueError('Another project package operation is running')
        try:
            yield
        finally:
            self.lock.release()

    def path(self, bundle_id):
        bundle_id = identifier(bundle_id)
        path = self.root/(bundle_id+'.zip')
        if (self.project not in self.root.resolve().parents or self.root.is_symlink() or
                path.is_symlink() or path.resolve().parent != self.root.resolve()):
            raise ValueError('Invalid staged package path')
        return path

    def _summary(self, bundle_id, manifest, files):
        heads = [json.loads(data) for name,data in files.items() if name.endswith('/head.json')]
        return {'ok':True,'bundle_id':bundle_id,'manifest':manifest,'scenes':heads,
                'archive':str(self.path(bundle_id)), 'live_world_modified':False,
                'dependency_availability':'not_checked',
                'download_url':'/projects/bundle/download?bundle_id='+bundle_id}

    def inspect(self, bundle_id):
        with self.operation():
            manifest, files = read_bundle(self.path(bundle_id))
            return self._summary(bundle_id, manifest, files)

    def export(self, data):
        if not isinstance(data,dict) or set(data)-{'scene_ids','include_material_previews'}:
            raise ValueError('Expected scene IDs and optional material preview flag')
        ids=data.get('scene_ids')
        previews=data.get('include_material_previews',False)
        if (not isinstance(ids,list) or not 1<=len(ids)<=100 or
                any(not isinstance(value,str) for value in ids) or len(set(ids))!=len(ids) or type(previews) is not bool):
            raise ValueError('Choose 1..100 unique saved scenes; preview flag must be boolean')
        for scene_id in ids: identifier(scene_id)
        with self.operation():
            self.path('validation')  # Reject redirected roots before any write.
            self.root.mkdir(parents=True,exist_ok=True)
            bundle_id=uuid.uuid4().hex
            partial=self.root/(bundle_id+'.partial')
            export_bundle(self.project/'data/scenes',self.project/'data',ids,partial,
                          include_material_previews=previews)
            manifest,files=read_bundle(partial)
            partial.replace(self.path(bundle_id))
            result=self._summary(bundle_id,manifest,files)
            result['scope']='Saved scene histories and referenced textures; generated source packages and model references require the CLI export workflow'
            return result

    def upload(self, payload):
        if not isinstance(payload,bytes) or not 0<len(payload)<=UPLOAD_LIMIT:
            raise ValueError('Browser uploads require a ZIP of at most 16 MiB; use the CLI for larger packages')
        with self.operation():
            manifest,files=read_bundle(io.BytesIO(payload))
            self.path('validation')
            self.root.mkdir(parents=True,exist_ok=True)
            bundle_id=uuid.uuid4().hex
            partial=self.root/(bundle_id+'.partial')
            with partial.open('xb') as stream:
                stream.write(payload);stream.flush();os.fsync(stream.fileno())
            partial.replace(self.path(bundle_id))
            return self._summary(bundle_id,manifest,files)

    def import_isolated(self, data):
        if (not isinstance(data,dict) or set(data)!={'bundle_id','confirmed'} or data['confirmed'] is not True):
            raise ValueError('Explicit confirmation and bundle ID required')
        with self.operation():
            source=self.path(data['bundle_id'])
            read_bundle(source)
            parent=self.project/'data/imported-projects'
            if parent.is_symlink() or self.project not in parent.resolve().parents:
                raise ValueError('Invalid isolated import root')
            parent.mkdir(parents=True,exist_ok=True)
            destination=import_bundle(source,parent)
            return {'ok':True,'bundle_id':data['bundle_id'],'directory':str(destination),
                    'live_world_modified':False,'active_scene_catalog_modified':False,
                    'dependency_availability':'not_checked','unreal_registered':False}

    def download(self, bundle_id):
        with self.operation():
            path=self.path(bundle_id)
            read_bundle(path)
            return path.read_bytes()

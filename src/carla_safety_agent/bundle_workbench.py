"""Local UI packaging; isolated imports never install into the active project."""
import io
import json
import os
from pathlib import Path
import threading
import uuid
from contextlib import contextmanager

from .project_bundle import export_bundle, extend_bundle, import_bundle, read_bundle
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
        if not isinstance(data,dict) or set(data)-{'scene_ids','include_material_previews','include_generated_sources','runtime_reference'}:
            raise ValueError('Expected scene IDs and optional material preview flag')
        ids=data.get('scene_ids')
        previews=data.get('include_material_previews',False)
        sources=data.get('include_generated_sources',False)
        reference=data.get('runtime_reference')
        if (not isinstance(ids,list) or not 1<=len(ids)<=100 or
                any(not isinstance(value,str) for value in ids) or len(set(ids))!=len(ids) or type(previews) is not bool or type(sources) is not bool):
            raise ValueError('Choose 1..100 unique saved scenes; preview flag must be boolean')
        for scene_id in ids: identifier(scene_id)
        if reference is not None:
            from .runtime_reference import validate_reference
            validate_reference(reference)
            if len(json.dumps(reference).encode())>1024*1024:
                raise ValueError('Runtime reference exceeds 1 MiB')
        with self.operation():
            self.path('validation')  # Reject redirected roots before any write.
            self.root.mkdir(parents=True,exist_ok=True)
            bundle_id=uuid.uuid4().hex
            partial=self.root/(bundle_id+'.partial')
            export_bundle(self.project/'data/scenes',self.project/'data',ids,partial,
                          include_material_previews=previews)
            manifest,files=read_bundle(partial)
            if sources or reference is not None:
                work=self.root/(bundle_id+'-sources')
                work.mkdir(exist_ok=False)
                bindings=self._source_packages(manifest,work) if sources else None
                reference_path=None
                if reference is not None:
                    reference_path=work/'reference.json'
                    with reference_path.open('x') as stream:
                        json.dump(reference,stream);stream.flush();os.fsync(stream.fileno())
                extended=self.root/(bundle_id+'.extended.partial')
                extend_bundle(partial,extended,generated_assets=bindings or None,runtime_reference=reference_path)
                partial=extended
                manifest,files=read_bundle(partial)
            partial.replace(self.path(bundle_id))
            result=self._summary(bundle_id,manifest,files)
            result['scope']='Saved scene snapshot with explicitly selected source packages/reference hashes; no weights, datasets, Unreal binaries or execution environment'
            return result

    def _source_packages(self, manifest, work):
        from .blender_pipeline import BlenderPipeline
        from .blender_package import export_asset
        blueprints=[value for value in manifest['dependencies']['blueprints'] if value.startswith('generated.prop.')]
        if not blueprints:return {}
        pipeline=BlenderPipeline(self.project)
        registry=pipeline.registry()
        root=self.project/'.runtime/blender-assets'
        if root.is_symlink() or self.project not in root.resolve().parents:
            raise ValueError('Generated source root is redirected')
        bindings={}
        for blueprint in blueprints:
            entry=registry.get(blueprint)
            if not entry or not isinstance(entry.get('source_fbx'),str):
                raise ValueError('Generated source is not registered: '+blueprint)
            source=Path(entry['source_fbx'])
            folder=source.parent
            if (source.name!='asset.fbx' or source.is_symlink() or folder.is_symlink() or
                    folder.resolve().parent!=root.resolve() or not source.is_file()):
                raise ValueError('Generated source must be a local asset job: '+blueprint)
            identifier(folder.name)
            request=folder/'request.json'
            if request.is_symlink() or not request.is_file() or request.stat().st_size>1024*1024:
                raise ValueError('Generated source parameters missing or unsafe: '+blueprint)
            parameters=json.loads(request.read_text())
            if not isinstance(parameters,dict):raise ValueError('Invalid generated source parameters')
            texture=parameters.get('texture_path')
            if texture is not None and (not isinstance(texture,str) or Path(texture).resolve()!=(folder/'texture.png').resolve() or not (folder/'texture.png').is_file()):
                raise ValueError('Generated texture must be inside its asset job')
            output=work/(str(len(bindings))+'.zip')
            export_asset(folder,output,{key:parameters.get(key) for key in ('color','roughness')})
            bindings[blueprint]=output
        return bindings

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

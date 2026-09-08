"""Bounded portable Blender source assets; unpacking does not execute assets."""
import hashlib
import json
import math
from pathlib import Path
import uuid
import zipfile

from .experiment_matrix import canonical

LIMIT = 256*1024*1024
ALLOWED = {'asset.fbx', 'asset.blend', 'asset.glb', 'texture.png'}


def material_parameters(value):
    if not isinstance(value, dict) or set(value) != {'color', 'roughness'}:
        raise ValueError('Explicit color and roughness are required')
    color, roughness = value['color'], value['roughness']
    numbers = color+[roughness] if isinstance(color,list) and len(color)==4 else []
    if len(numbers)!=5 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not 0<=v<=1 for v in numbers):
        raise ValueError('RGBA and roughness must be finite values in 0..1')
    return value


def export_asset(folder, output, parameters):
    """Caller explicitly selects the source folder and material parameters."""
    parameters = material_parameters(parameters)
    folder = Path(folder); files = {}; total = 0
    for name in sorted(ALLOWED):
        path = folder/name
        if not path.exists(): continue
        if path.is_symlink() or not path.is_file() or path.stat().st_size > LIMIT-total:
            raise ValueError('Invalid asset file or package too large')
        payload = path.read_bytes(); total += len(payload)
        if total > LIMIT: raise ValueError('Asset package too large')
        files[name] = payload
    if not files.get('asset.fbx'): raise ValueError('A nonempty asset.fbx is required')
    manifest = {'schema_version':'carla-blender-package/1','material':parameters,
                'files':{name:{'size':len(payload),'sha256':hashlib.sha256(payload).hexdigest()} for name,payload in files.items()},
                'unreal_registered':False}
    with Path(output).open('xb') as stream, zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('manifest.json',canonical(manifest))
        for name,payload in files.items(): archive.writestr(name,payload)
    return manifest


def read_asset(path):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if (len(names)!=len(set(names)) or not {'manifest.json','asset.fbx'}<=set(names)
                or set(names)-ALLOWED-{'manifest.json'} or sum(info.file_size for info in archive.infolist())>LIMIT+8192
                or archive.getinfo('manifest.json').file_size>8192):
            raise ValueError('Invalid asset archive entries or size')
        manifest = json.loads(archive.read('manifest.json'))
        if manifest.get('schema_version')!='carla-blender-package/1' or manifest.get('unreal_registered') is not False:
            raise ValueError('Invalid asset package schema')
        material_parameters(manifest['material'])
        if set(manifest['files'])!=set(names)-{'manifest.json'}: raise ValueError('Asset manifest files mismatch')
        files = {name:archive.read(name) for name in manifest['files']}
        for name,payload in files.items():
            if manifest['files'][name]!={'size':len(payload),'sha256':hashlib.sha256(payload).hexdigest()}:
                raise ValueError('Asset checksum mismatch')
        if not files['asset.fbx']: raise ValueError('Empty FBX')
    return manifest,files


def import_asset(path, project_root):
    manifest,files = read_asset(path)
    job_id = uuid.uuid4().hex
    folder = Path(project_root)/'.runtime/blender-assets'/job_id
    folder.mkdir(parents=True,exist_ok=False)
    for name,payload in files.items(): (folder/name).write_bytes(payload)
    request = {**manifest['material']}
    if 'texture.png' in files: request['texture_path']=str((folder/'texture.png').resolve())
    outputs = {extension:str((folder/('asset.'+extension)).resolve()) for extension in ('fbx','blend','glb') if 'asset.'+extension in files}
    (folder/'request.json').write_bytes(canonical(request))
    (folder/'manifest.json').write_bytes(canonical({'outputs':outputs,'name':'Imported_'+job_id,
        'source_package':manifest,'requires_unreal_import':True}))
    return {'job_id':job_id,'directory':str(folder.resolve()),'unreal_registered':False,'asset_executed':False}

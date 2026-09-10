"""Add verified exported previews without replacing existing actor definitions."""
import fcntl
import json
from pathlib import Path
from .material_mesh import validate_preview
from .material_library import material_edits
from .scene_store import atomic, identifier


def merge_preview_catalog(source, data_root):
    source = Path(source).resolve()
    if source.stat().st_size>8*1024*1024: raise ValueError('Oversized material catalog')
    catalog = json.loads(source.read_text())
    if catalog.get('schema_version') != 'carla-material-catalog/1' or not catalog.get('actors'):
        raise ValueError('Invalid or empty material catalog')
    town = identifier(catalog['map'].split('/')[-1])
    payloads = {}
    identities = []
    for target, entries in catalog['actors'].items():
        if not isinstance(target,str) or not target or '|' in target or not entries:
            raise ValueError('Invalid material target')
        for entry in entries:
            for slot in entry.get('slots',[]):
                if slot.get('status') != 'uv0_ready': continue
                identities.append({'target':target,'component':entry.get('component'),
                                   'slot':slot.get('slot'),'texture':'0'*64})
                name = slot['mesh_file']
                if not isinstance(name,str) or Path(name).name != name or name in ('.','..') or not name.endswith('.json'):
                    raise ValueError('Invalid preview path')
                path = source.parent/name
                if path.is_symlink() or path.stat().st_size>32*1024*1024:
                    raise ValueError('Invalid preview file')
                payload = path.read_bytes()
                value = validate_preview(payload)
                if value['triangleCount'] != slot['triangles']:
                    raise ValueError('Preview triangle count mismatch')
                payloads[name] = payload
    material_edits(identities)
    if not payloads: raise ValueError('No verified preview meshes')
    folder = Path(data_root)/'material-exports'/town
    folder.mkdir(parents=True,exist_ok=True)
    with (folder/'merge.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        destination = folder/'preview-catalog.json'
        previous = json.loads(destination.read_text()) if destination.exists() else {
            'schema_version':'carla-material-catalog/1','map':catalog['map'],'actors':{}}
        if previous.get('map') != catalog['map']: raise ValueError('Catalog map mismatch')
        for target, entries in catalog['actors'].items():
            if target in previous['actors'] and previous['actors'][target] != entries:
                raise ValueError('Existing actor definition differs: '+target)
        for name,payload in payloads.items():
            path = folder/name
            if path.is_symlink() or (path.exists() and path.read_bytes()!=payload):
                raise ValueError('Existing preview file differs: '+name)
        for name,payload in payloads.items():
            try:
                with (folder/name).open('xb') as stream: stream.write(payload)
            except FileExistsError:
                if (folder/name).read_bytes()!=payload: raise ValueError('Preview changed during merge')
        previous['actors'].update(catalog['actors'])
        atomic(destination,previous)
    return {'catalog':str(destination),'added_or_verified':sorted(catalog['actors']),
            'mesh_count':len(payloads),'world_modified':False}

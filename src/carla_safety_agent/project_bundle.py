"""Portable scene history and referenced textures; never extracts arbitrary paths."""
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import tempfile
import zipfile

from .experiment_matrix import canonical
from .material_library import material_edits
from .material_mesh import validate_preview
from .scene_store import SceneStore, identifier, validate_scene
from .blender_package import read_asset, import_asset
from .actor_materials import actor_texture_digests

LIMIT = 256 * 1024 * 1024
SCHEMA = 'carla-project-bundle/1'
ENTRY = re.compile(r'(?:scenes/[A-Za-z0-9_-]{1,80}/[A-Za-z0-9_-]{1,80}\.json|textures/[a-f0-9]{64}\.png|material-exports/[A-Za-z0-9_-]{1,80}/[A-Za-z0-9_-]{1,120}\.json|generated-assets/(?:index\.json|[a-f0-9]{64}\.zip)|runtime/reference\.json)')


def _validate(files):
    scenes = {}; maps = set(); blueprints = set(); slots = set(); textures = set(); actor_slots=set();has_actor_materials=False
    for name, payload in files.items():
        if not ENTRY.fullmatch(name):
            raise ValueError('Unsupported bundle path')
        if name.startswith(('material-exports/', 'generated-assets/', 'runtime/')):
            continue
        if name.startswith('textures/'):
            if hashlib.sha256(payload).hexdigest() != Path(name).stem:
                raise ValueError('Texture checksum mismatch')
            continue
        _, scene_id, filename = name.split('/')
        scenes.setdefault(scene_id, {})[filename] = json.loads(payload)
    for scene_id, documents in scenes.items():
        head = documents.get('head.json', {})
        history = head.get('history')
        cursor = head.get('cursor')
        if (not isinstance(history, list) or not history or len(set(history)) != len(history)
                or isinstance(cursor, bool) or not isinstance(cursor, int) or not 0 <= cursor < len(history)
                or head.get('scene_id') != scene_id or head.get('version') != history[cursor]):
            raise ValueError('Invalid scene history')
        if set(documents) != {'head.json', *(identifier(version)+'.json' for version in history)}:
            raise ValueError('Scene history files do not match head')
        for version in history:
            document = validate_scene(documents[version+'.json'])
            if document.get('scene_id') != scene_id or document.get('version') != version:
                raise ValueError('Scene version identity mismatch')
            maps.add(document['map'])
            blueprints.update(obj['blueprint_id'] for obj in document['objects'])
            edits = material_edits(document.get('environment_materials', []))
            textures.update(edits.values())
            textures.update(actor_texture_digests(document))
            if 'actor_materials' in document:
                has_actor_materials=True
                actor_slots.update((record['blueprint_id'],record['component'],record['slot']) for record in document['actor_materials'])
            slots.update((document['map'], *key) for key in edits)
    if not scenes:
        raise ValueError('Bundle requires scenes')
    if {name for name in files if name.startswith('textures/')} != {f'textures/{digest}.png' for digest in textures}:
        raise ValueError('Missing or unreferenced textures')
    preview_files = {name for name in files if name.startswith('material-exports/')}
    if preview_files:
        expected = set()
        for map_name, target, component, slot in slots:
            town = identifier(map_name.split('/')[-1])
            catalog_name = f'material-exports/{town}/preview-catalog.json'
            catalog = json.loads(files[catalog_name])
            matches = [s for entry in catalog['actors'].get(target, []) if entry['component'] == component
                       for s in entry['slots'] if s['slot'] == slot and s.get('status') == 'uv0_ready']
            if len(matches) != 1: raise ValueError('Missing or ambiguous preview slot')
            mesh = matches[0]['mesh_file']
            if not isinstance(mesh, str) or Path(mesh).name != mesh: raise ValueError('Invalid mesh filename')
            mesh_name = f'material-exports/{town}/{mesh}'
            if mesh_name not in files: raise ValueError('Missing preview mesh')
            validate_preview(files[mesh_name])
            expected.update((catalog_name, mesh_name))
        if preview_files != expected: raise ValueError('Unexpected preview files')
    dependencies = {'maps': sorted(maps), 'blueprints': sorted(blueprints),
            'material_slots': [list(slot) for slot in sorted(slots)],
            'external_assets_included': False, 'weights_included': False,
            'execution_history_included': False, 'datasets_included': False}
    if has_actor_materials:dependencies['actor_material_slots']=[list(slot) for slot in sorted(actor_slots)]
    asset_files = {name for name in files if name.startswith('generated-assets/')}
    if asset_files:
        if 'generated-assets/index.json' not in files:
            raise ValueError('Missing generated asset index')
        bindings = json.loads(files['generated-assets/index.json'])
        expected_blueprints = {bp for bp in blueprints if bp.startswith('generated.prop.')}
        if not isinstance(bindings, dict) or not bindings or set(bindings) != expected_blueprints:
            raise ValueError('Generated asset bindings must cover exactly the referenced generated blueprints')
        expected_files = {'generated-assets/index.json'}
        expanded = sum(map(len, files.values()))
        for blueprint, digest in bindings.items():
            if not isinstance(digest, str) or not re.fullmatch('[a-f0-9]{64}', digest):
                raise ValueError('Invalid generated asset package digest')
            name = f'generated-assets/{digest}.zip'
            if name not in files or hashlib.sha256(files[name]).hexdigest() != digest:
                raise ValueError('Generated asset package missing or checksum mismatch')
            if name not in expected_files:
                with zipfile.ZipFile(io.BytesIO(files[name])) as nested:
                    nested_size = sum(info.file_size for info in nested.infolist())
                if expanded + nested_size > LIMIT:
                    raise ValueError('Expanded generated assets exceed bundle size limit')
                _, source_files = read_asset(io.BytesIO(files[name]))
                expanded += sum(map(len, source_files.values()))
                if expanded > LIMIT:
                    raise ValueError('Expanded generated assets exceed bundle size limit')
            expected_files.add(name)
        if asset_files != expected_files:
            raise ValueError('Unreferenced generated asset packages')
        dependencies['generated_asset_sources'] = dict(sorted(bindings.items()))
        dependencies['generated_assets_require_unreal_import'] = True
        dependencies['external_assets_included'] = True
        dependencies['unreal_asset_binaries_included'] = False
    if 'runtime/reference.json' in files:
        from .runtime_reference import validate_reference
        if len(files['runtime/reference.json'])>1024*1024:raise ValueError('Runtime reference exceeds 1 MiB')
        reference=validate_reference(json.loads(files['runtime/reference.json']))
        dependencies['runtime_reference_included']=True
        dependencies['model_ids']=sorted({entry['model'] for entry in reference['files']})
    return dependencies


def export_bundle(scene_root, material_root, scene_ids, output, *, include_material_previews=False,
                  generated_assets=None, runtime_reference=None):
    files = {}; total = 0
    def add(name, path):
        nonlocal total
        path = Path(path)
        if path.is_symlink() or not path.is_file() or path.stat().st_size > LIMIT-total:
            raise ValueError('Invalid source file or bundle size')
        payload = path.read_bytes(); total += len(payload)
        if total > LIMIT: raise ValueError('Bundle exceeds size limit')
        files[name] = payload
    store = SceneStore(scene_root)
    for scene_id in dict.fromkeys(scene_ids):
        scene_id = identifier(scene_id)
        folder = store.root/scene_id
        if folder.is_symlink() or not folder.is_dir(): raise ValueError('Unknown scene')
        with store.locked(scene_id):
            add(f'scenes/{scene_id}/head.json', folder/'head.json')
            head = json.loads(files[f'scenes/{scene_id}/head.json'])
            for version in head['history']:
                name = f'scenes/{scene_id}/{identifier(version)}.json'
                add(name, folder/(version+'.json'))
                document = validate_scene(json.loads(files[name]))
                for digest in set(material_edits(document.get('environment_materials', [])).values())|actor_texture_digests(document):
                    texture = f'textures/{digest}.png'
                    if texture not in files: add(texture, Path(material_root)/texture)
    dependencies = _validate(files)
    if include_material_previews:
        catalogs = {}
        for map_name, target, component, slot in dependencies['material_slots']:
            town = identifier(map_name.split('/')[-1])
            catalog_name = f'material-exports/{town}/preview-catalog.json'
            source_path = Path(material_root)/catalog_name
            if source_path.is_symlink() or source_path.stat().st_size > 8*1024*1024:
                raise ValueError('Invalid preview catalog')
            source = json.loads(source_path.read_bytes())
            entries = [entry for entry in source['actors'].get(target, []) if entry['component'] == component]
            slots = [(entry, s) for entry in entries for s in entry['slots']
                     if s['slot'] == slot and s.get('status') == 'uv0_ready']
            if len(slots) != 1: raise ValueError('Missing or ambiguous source preview')
            entry, value = slots[0]
            mesh_name = f'material-exports/{town}/{value["mesh_file"]}'
            if not ENTRY.fullmatch(mesh_name): raise ValueError('Invalid source preview path')
            if mesh_name not in files: add(mesh_name, Path(material_root)/mesh_name)
            catalog = catalogs.setdefault(catalog_name, {**source, 'actors': {}})
            components = catalog['actors'].setdefault(target, [])
            chosen = next((item for item in components if item['component'] == component), None)
            if chosen is None:
                chosen = {**entry, 'slots': []}; components.append(chosen)
            if value not in chosen['slots']: chosen['slots'].append(value)
        for name, catalog in catalogs.items(): files[name] = canonical(catalog)
        if sum(map(len, files.values())) > LIMIT: raise ValueError('Bundle exceeds size limit')
        _validate(files)
    return _write_bundle(files, output, generated_assets=generated_assets, runtime_reference=runtime_reference)


def extend_bundle(source, output, *, generated_assets=None, runtime_reference=None):
    """Extend the validated snapshot, without rereading changing scene histories."""
    _, files = read_bundle(source)
    if any(name.startswith(('generated-assets/', 'runtime/')) for name in files):
        raise ValueError('Only a scene snapshot without source bindings can be extended')
    return _write_bundle(files, output, generated_assets=generated_assets, runtime_reference=runtime_reference)


def _write_bundle(files, output, *, generated_assets=None, runtime_reference=None):
    _validate(files)
    if generated_assets is not None:
        bindings = {}
        for blueprint, package in generated_assets.items():
            package = Path(package)
            if package.is_symlink() or not package.is_file() or package.stat().st_size > LIMIT:
                raise ValueError('Invalid generated asset source package')
            payload = package.read_bytes()
            digest = hashlib.sha256(payload).hexdigest()
            if f'generated-assets/{digest}.zip' not in files and sum(map(len, files.values())) + len(payload) > LIMIT:
                raise ValueError('Bundle exceeds size limit')
            files[f'generated-assets/{digest}.zip'] = payload
            bindings[blueprint] = digest
        files['generated-assets/index.json'] = canonical(bindings)
    if runtime_reference is not None:
        path = Path(runtime_reference)
        if path.is_symlink() or not path.is_file() or path.stat().st_size>1024*1024:
            raise ValueError('Invalid runtime reference or exceeds 1 MiB')
        files['runtime/reference.json'] = path.read_bytes()
    if sum(map(len, files.values())) > LIMIT: raise ValueError('Bundle exceeds size limit')
    dependencies = _validate(files)
    manifest = {'schema_version': SCHEMA, 'dependencies': dependencies,
                'files': {name: {'sha256': hashlib.sha256(payload).hexdigest(), 'size': len(payload)}
                          for name, payload in sorted(files.items())}}
    # Exclusive create: an existing archive is never replaced.
    with Path(output).open('xb') as stream, zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('manifest.json', canonical(manifest))
        for name, payload in sorted(files.items()): archive.writestr(name, payload)
    return manifest


def read_bundle(path):
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        names = [entry.filename for entry in entries]
        if (len(names) > 10000 or len(names) != len(set(names)) or 'manifest.json' not in names
                or sum(entry.file_size for entry in entries) > LIMIT+8*1024*1024
                or any(name != 'manifest.json' and not ENTRY.fullmatch(name) for name in names)):
            raise ValueError('Invalid archive entries or size')
        if archive.getinfo('manifest.json').file_size > 8*1024*1024:
            raise ValueError('Manifest too large')
        manifest = json.loads(archive.read('manifest.json'))
        if manifest.get('schema_version') != SCHEMA or set(manifest.get('files', {})) != set(names)-{'manifest.json'}:
            raise ValueError('Invalid bundle manifest')
        files = {}
        for name, expected in manifest['files'].items():
            payload = archive.read(name)
            if expected != {'size': len(payload), 'sha256': hashlib.sha256(payload).hexdigest()}:
                raise ValueError('Bundle checksum mismatch')
            files[name] = payload
    if manifest['dependencies'] != _validate(files): raise ValueError('Dependency manifest mismatch')
    return manifest, files


def import_bundle(path, destination_parent):
    manifest, files = read_bundle(path)  # Validate everything before allocating output.
    destination = Path(tempfile.mkdtemp(prefix='carla-project-', dir=destination_parent))
    try:
        for name, payload in files.items():
            target = destination/'data'/name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
        (destination/'manifest.json').write_bytes(canonical(manifest))
    except BaseException:
        shutil.rmtree(destination)  # Only the private directory allocated above.
        raise
    return destination


def prepare_generated_assets(path, project_root):
    """Validate the whole bundle, then stage jobs; never execute or register assets."""
    manifest, files = read_bundle(path)
    bindings = manifest['dependencies'].get('generated_asset_sources', {})
    if not bindings:
        raise ValueError('Bundle contains no generated asset source packages')
    jobs = {}; prepared_packages = {}
    for blueprint, digest in bindings.items():
        if digest not in prepared_packages:
            prepared_packages[digest] = import_asset(io.BytesIO(files[f'generated-assets/{digest}.zip']), project_root)
        job = prepared_packages[digest]
        jobs[blueprint] = {**job, 'source_package_sha256': digest,
                           'suggested_asset_name': blueprint.removeprefix('generated.prop.')}
    return {'assets': jobs, 'unreal_registered': False, 'live_world_modified': False,
            'requires_explicit_unreal_import': True}

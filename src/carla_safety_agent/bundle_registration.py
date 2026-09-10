"""Explicit native imports with unique names and a separate remapped scene bundle."""
import hashlib
import io
import json
from pathlib import Path
import uuid
import zipfile

from .blender_package import import_asset
from .blender_pipeline import BlenderPipeline
from .experiment_matrix import canonical
from .project_bundle import read_bundle, _validate, SCHEMA


def register_bundle(path, project_root, output, *, execute=False):
    if not execute:
        raise ValueError('Explicit execute=True is required to launch Unreal imports')
    manifest, files = read_bundle(path)
    bindings = manifest['dependencies'].get('generated_asset_sources', {})
    if not bindings:
        raise ValueError('Bundle has no generated source assets')
    output = Path(output)
    if output.exists():
        raise ValueError('Output bundle already exists')
    pipeline = BlenderPipeline(Path(project_root))
    if not pipeline.importer.is_file():
        raise ValueError('Target must be an installed project containing the Unreal importer')
    operation = uuid.uuid4().hex
    folder = pipeline.runtime/'migrations'/operation
    folder.mkdir(parents=True, exist_ok=False)
    report = {'operation_id':operation, 'state':'running', 'assets':{},
              'live_world_modified':False, 'restored':False, 'output':str(output.resolve())}
    def save():
        temporary = folder/'report.tmp'
        temporary.write_bytes(canonical(report))
        temporary.replace(folder/'report.json')
    save()
    try:
        replacements = {}
        for index, (original, digest) in enumerate(sorted(bindings.items())):
            asset_name = f'Migrated_{operation[:20]}_{index}'
            job = import_asset(io.BytesIO(files[f'generated-assets/{digest}.zip']), project_root)
            entry = {'state':'importing', 'job_id':job['job_id'], 'asset_name':asset_name,
                     'source_package_sha256':digest}
            report['assets'][original] = entry
            save()  # A crash here leaves an uncertain import, never an implicit retry.
            result = pipeline.import_to_carla(job['job_id'], asset_name, require_clean_exit=True)
            expected = 'generated.prop.' + asset_name.lower()
            if result.get('blueprint_id') != expected or result.get('import_returncode') != 0:
                raise RuntimeError('Imported asset identity or clean exit not verified')
            entry.update(state='registered', blueprint_id=expected, import_log=result['import_log'])
            replacements[original] = expected
            save()
        for name in list(files):
            if name.startswith('scenes/') and not name.endswith('/head.json'):
                document = json.loads(files[name])
                for obj in document['objects']:
                    obj['blueprint_id'] = replacements.get(obj['blueprint_id'], obj['blueprint_id'])
                files[name] = canonical(document)
        files['generated-assets/index.json'] = canonical({replacements[bp]:digest for bp,digest in bindings.items()})
        dependencies = _validate(files)
        exported = {'schema_version':SCHEMA, 'dependencies':dependencies,
                    'files':{name:{'size':len(payload),'sha256':hashlib.sha256(payload).hexdigest()}
                             for name,payload in sorted(files.items())}}
        with output.open('xb') as stream, zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('manifest.json',canonical(exported))
            for name,payload in sorted(files.items()): archive.writestr(name,payload)
        read_bundle(output)
        report.update(state='registered', blueprint_replacements=replacements)
        save()
    except BaseException as exc:
        report.update(state='needs_attention', error=str(exc))
        save()
        raise RuntimeError(f'Migration incomplete; retained assets/jobs and report: {folder / "report.json"}') from exc
    return {**report, 'report':str(folder/'report.json')}

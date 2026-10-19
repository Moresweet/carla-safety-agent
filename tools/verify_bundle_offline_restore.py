"""Import into a new directory and verify every scene/asset byte; no CARLA RPC."""
import argparse
import hashlib
import io
import json
from pathlib import Path
from carla_safety_agent.project_bundle import read_bundle, import_bundle, prepare_generated_assets
from carla_safety_agent.blender_package import read_asset


def verify(archive, destination_parent):
    archive = Path(archive)
    before = hashlib.sha256(archive.read_bytes()).hexdigest()
    manifest, files = read_bundle(archive)
    destination = import_bundle(archive, destination_parent)
    for name, payload in files.items():
        if (destination/'data'/name).read_bytes() != payload:
            raise ValueError(f'Imported payload mismatch: {name}')
    checked = 0
    if manifest['dependencies'].get('generated_asset_sources'):
        prepared = prepare_generated_assets(archive, destination)
        for blueprint, job in prepared['assets'].items():
            digest = job['source_package_sha256']
            _, sources = read_asset(io.BytesIO(files[f'generated-assets/{digest}.zip']))
            for name, payload in sources.items():
                if (Path(job['directory'])/name).read_bytes() != payload:
                    raise ValueError(f'Asset source mismatch: {blueprint}/{name}')
                checked += 1
            request = json.loads((Path(job['directory'])/'request.json').read_text())
            if 'texture.png' in sources and request.get('texture_path') != str((Path(job['directory'])/'texture.png').resolve()):
                raise ValueError('Texture path was not remapped to the imported project')
    if hashlib.sha256(archive.read_bytes()).hexdigest() != before:
        raise ValueError('Source archive changed during verification')
    return {'ok':True, 'archive':str(archive.absolute()), 'archive_sha256':before,
            'destination':str(destination.absolute()), 'verified_payloads':len(files),
            'verified_asset_sources':checked, 'live_world_modified':False,
            'limitations':['Offline byte/path validation only; no Unreal import, Blueprint registration or CARLA restore',
                           'New verification directory retained; not a cross-machine environment test']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--destination-parent', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink(): parser.error('Receipt already exists')
    result = verify(args.archive, args.destination_parent)
    with args.output.open('x') as stream: json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__': main()

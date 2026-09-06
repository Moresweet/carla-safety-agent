#!/usr/bin/env python3
"""Export allowlisted local dependencies without credentials or host configuration."""
import argparse
import hashlib
import json
import shutil
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXCLUDED = {'.git', '.ssh', '.aws', '.azure', '.kube', '.codex', '__pycache__',
            'Intermediate', 'DerivedDataCache', 'Saved', '.pytest_cache', '.npmrc',
            '.pypirc', '.netrc', '.bash_history'}

def filter_member(member):
    parts = Path(member.name).parts
    if any(p in EXCLUDED or p.startswith('.env') for p in parts):
        return None
    if member.name.endswith(('.debug', '.sym', '.pdb', '.log')):
        return None
    if not (member.isfile() or member.isdir() or member.issym() or member.islnk()):
        return None
    member.uid = member.gid = 1000
    member.uname = member.gname = 'researcher'
    return member

def command(*args):
    return subprocess.check_output(args, text=True).strip()

def archive(destination, paths, relative_to=Path('/')):
    if destination.exists():
        raise RuntimeError(f'Refusing to overwrite {destination}; use a new snapshot directory')
    with tarfile.open(destination, 'w') as output:
        for path in paths:
            print(f'Packing {path}', flush=True)
            output.add(path, arcname=str(path.relative_to(relative_to)), filter=filter_member)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('destination', type=Path)
    parser.add_argument('--finalize-only', action='store_true', help='Export small license/launcher overlay for an existing image')
    args = parser.parse_args()
    dest = args.destination.resolve()
    dest.mkdir(parents=True, exist_ok=True)
    manifests = dest / 'manifest'
    manifests.mkdir(exist_ok=True)
    carla = Path('/home/moresweet/carla')
    engine = Path('/home/moresweet/UnrealEngine_4.26')
    e2e = Path('/home/moresweet/Data/e2e')
    if args.finalize_only:
        archive(dest/'licenses.tar', [engine/'LICENSE.md', carla/'LICENSE'])
        shutil.copy2(ROOT/'integration/docker/Dockerfile.finalize', dest/'Dockerfile')
        shutil.copy2(ROOT/'integration/docker/entrypoint.sh', dest/'entrypoint.sh')
        return
    subprocess.run(['python3', str(ROOT/'integration/carla/verify_external_environment.py'),
                    '--carla-root', str(carla)], check=True)
    # Record local source changes separately from binary assets; suppress Git LFS filters.
    for name, path in [('carla', carla), ('engine', engine),
                       ('bench2drive', e2e/'Bench2Drive'), ('zoo', e2e/'Bench2DriveZoo')]:
        (manifests/f'{name}-commit.txt').write_text(command('git', '-C', str(path), 'rev-parse', 'HEAD')+'\n')
        diff = command('git', '-C', str(path), '-c', 'filter.lfs.process=',
                       '-c', 'filter.lfs.required=false', 'diff', '--no-ext-diff', '--',
                       '*.cpp', '*.h', '*.py', '*.sh', '*.cs', '*.ini', '*.Build.cs')
        (manifests/f'{name}-source.patch').write_text(diff+'\n')
    (manifests/'host-packages.tsv').write_text(command('dpkg-query', '-W', '-f=${Package}\t${Version}\n')+'\n')
    (manifests/'uniad-pip.json').write_text(command(str(e2e/'miniconda3/envs/uniad-cu128/bin/python'),
                                               '-m', 'pip', 'list', '--format=json')+'\n')
    engine_paths = [engine/'Engine', engine/'LICENSE.md']
    if (engine/'FeaturePacks').exists():
        engine_paths.append(engine/'FeaturePacks')
    archive(dest/'engine.tar', engine_paths)
    archive(dest/'carla.tar', [carla/'Unreal', carla/'PythonAPI', carla/'.venv', carla/'LibCarla', carla/'Util', carla/'LICENSE'])
    archive(dest/'e2e.tar', [e2e/'Bench2Drive', e2e/'Bench2DriveZoo', e2e/'miniconda3/envs/uniad-cu128'])
    archive(dest/'ros.tar', [Path('/opt/ros/lyrical')])
    frontend = ROOT/'tools/livery-designer'
    archive(dest/'frontend-deps.tar', [frontend/'node_modules'], frontend)
    node = Path('/home/moresweet/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node')
    shutil.copy2(node, dest/'node')
    for name in ['Dockerfile', 'entrypoint.sh']:
        shutil.copy2(ROOT/'integration/docker'/name, dest/name)
    records = {}
    for path in sorted(dest.glob('*.tar')):
        print(f'Hashing {path.name}', flush=True)
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        records[path.name] = {'bytes': path.stat().st_size, 'sha256': digest}
    (manifests/'archives.json').write_text(json.dumps(records, indent=2)+'\n')
    print(f'Snapshot ready: {dest}', flush=True)

if __name__ == '__main__':
    main()

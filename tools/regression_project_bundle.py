"""Read real saved material scenes, export/import offline, compare every byte."""
import json
import tempfile
from pathlib import Path

from carla_safety_agent.project_bundle import export_bundle, import_bundle, read_bundle
from carla_safety_agent.scene_store import SceneStore


def main():
    root = Path(__file__).resolve().parents[1]
    store = SceneStore(root/'data/scenes')
    chosen = []
    for head in store.list():
        if any(store.read(head['scene_id'], version)['document'].get('environment_materials')
               for version in head['history']):
            chosen.append(head['scene_id'])
        if len(chosen) == 3: break
    assert chosen, 'Need real saved material scenes'
    parent = root/'runs/validation'; parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='project-bundle-', dir=parent))
    archive = work/'project.zip'
    manifest = export_bundle(store.root, root/'data', chosen, archive)
    imported = import_bundle(archive, work)
    _, files = read_bundle(archive)
    for name, payload in files.items():
        assert (root/'data'/name).read_bytes() == payload
        assert (imported/'data'/name).read_bytes() == payload
    destination = SceneStore(imported/'data/scenes')
    for scene_id in chosen:
        assert destination.read(scene_id) == store.read(scene_id)
    result = {'passed': True, 'scene_ids': chosen, 'file_count': len(files),
              'texture_count': sum(name.startswith('textures/') for name in files),
              'archive': str(archive), 'imported': str(imported),
              'dependencies': manifest['dependencies'], 'live_restore_verified': False}
    (work/'report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == '__main__': main()

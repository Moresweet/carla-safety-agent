"""Read-only, path-confined dataset playback API helpers."""
import json
from pathlib import Path


def dataset_path(root, run_id):
    root = Path(root).resolve()
    path = (root/run_id).resolve()
    if path.parent != root or not (path/'manifest.json').is_file():
        raise ValueError('Unknown dataset')
    return path


def replay_index(root, run_id):
    path = dataset_path(root, run_id)
    if not (path/'index.json').is_file():
        return {'frames': [], 'legacy': True, 'message': '旧数据没有同步帧索引，不能冒充六视角回放'}
    return json.loads((path/'index.json').read_text())


def replay_file(root, run_id, frame, name):
    path = dataset_path(root, run_id)
    index = replay_index(root, run_id)
    entry = next((v for v in index['frames'] if v['frame'] == int(frame)), None)
    if not entry or Path(name).name != name:
        raise ValueError('Unknown frame/file')
    folder = (path/entry['path']).resolve()
    target = (folder/name).resolve()
    if not folder.is_relative_to(path) or target.parent != folder or not target.is_file():
        raise ValueError('File is outside this recorded frame')
    return target

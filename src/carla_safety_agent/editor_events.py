"""Map rule command attempts to the first recorded frame after their boundary."""
from bisect import bisect_right
import json
from pathlib import Path


def attach_editor_events(dataset, audit_dir, execution_id):
    """Finalize a portable copy; never trust result-provided arbitrary paths."""
    from .sensor_capture import atomic_json
    dataset, audit_dir = Path(dataset), Path(audit_dir)
    if not audit_dir.is_dir() or audit_dir.is_symlink():
        raise ValueError('Missing or invalid editor audit directory')
    manifest = json.loads((dataset/'manifest.json').read_text())
    if manifest.get('execution_id') != execution_id:
        raise ValueError('Dataset belongs to another execution')
    records = []
    paths = sorted(audit_dir.glob('*.json'))
    if len(paths)>10000:
        raise ValueError('Too many editor audit records')
    total = 0
    for path in paths:
        total += path.stat().st_size
        if path.is_symlink() or total>16*1024*1024:
            raise ValueError('Invalid or oversized editor audit archive')
        records.append(json.loads(path.read_text()))
    frames = [entry['frame'] for entry in json.loads((dataset/'index.json').read_text())['frames']]
    events = editor_events(records,frames,execution_id)
    atomic_json(dataset/'editor-events.json', {'schema_version':'carla-editor-events/1',
        'execution_id':execution_id,'records':records,'events':events})
    manifest.setdefault('files',{})['editor_events'] = 'editor-events.json'
    atomic_json(dataset/'manifest.json',manifest)
    return events


def editor_events(records, frames, execution_id):
    if not isinstance(execution_id,str) or not execution_id:
        raise ValueError('Execution identity required')
    if len(records)>10000 or len(frames)>10000:
        raise ValueError('Editor event indexing limit exceeded')
    if any(isinstance(f,bool) or not isinstance(f,int) or f<0 for f in frames):
        raise ValueError('Invalid recorded frame')
    if frames != sorted(set(frames)):
        raise ValueError('Frames must be strictly ordered')
    events, seen = [], set()
    for record in records:
        if record.get('execution_id') != execution_id:
            raise ValueError('Editor command belongs to another execution')
        identity = record.get('command_id')
        if not isinstance(identity,str) or not identity or identity in seen:
            raise ValueError('Invalid or duplicate command identity')
        seen.add(identity)
        before = record.get('observed_frame_before')
        if isinstance(before,bool) or not isinstance(before,int) or before<0:
            raise ValueError('Invalid command boundary')
        state = record.get('state')
        if state not in ('attempting','responded'):
            raise ValueError('Unknown command audit state')
        response = record.get('response') or {}
        certain = state=='responded' and record.get('observed_frame_after')==before and response.get('ok') is True
        position = bisect_right(frames,before)
        target = frames[position] if certain and position<len(frames) else None
        command = record.get('command') or {}
        events.append({'command_id':identity,'action':command.get('action'),
            'boundary_frame':before,'seek_frame':target,
            'outcome':'acknowledged' if certain else 'uncertain',
            'recording_relation':('before_recording' if target is not None and position==0
                                  else 'within_recording' if target is not None else 'unmapped'),
            'note':'First later recorded sample; not proof of visible effect or unchanged scene between samples'})
    return sorted(events,key=lambda e:(e['boundary_frame'],e['command_id']))

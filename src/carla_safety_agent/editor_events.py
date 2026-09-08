"""Map rule command attempts to the first recorded frame after their boundary."""
from bisect import bisect_right


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

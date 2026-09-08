import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from regression_rule_move import verify_recorded_move
from carla_safety_agent.editor_events import editor_events


@pytest.mark.parametrize('defect', [None, 'unchanged', 'early', 'missing', 'wrong_seek'])
def test_recorded_move_requires_pose_transition(tmp_path, defect):
    records = [{'execution_id': 'run', 'command_id': 'move', 'state': 'responded',
                'observed_frame_before': 10, 'observed_frame_after': 10,
                'command': {'action': 'update'}, 'response': {'ok': True}}]
    entries = []
    for frame, x in [(10, 245. if defect == 'early' else 240.),
                     (11, 240. if defect == 'unchanged' else 245.)]:
        folder = tmp_path/str(frame)
        folder.mkdir()
        actors = [{'id': 7, 'matrix': [[1, 0, 0, x]]}]
        if defect == 'missing' and frame == 11:
            actors = []
        (folder/'frame.json').write_text(json.dumps({'actors': actors}))
        entries.append({'frame': frame, 'path': str(frame)})
    (tmp_path/'index.json').write_text(json.dumps({'frames': entries}))
    events = editor_events(records, [10, 11], 'run')
    if defect == 'wrong_seek':
        events[0]['seek_frame'] = 10
    (tmp_path/'editor-events.json').write_text(json.dumps({
        'execution_id': 'run', 'records': records, 'events': events}))
    if defect:
        with pytest.raises(AssertionError):
            verify_recorded_move(tmp_path, 'run', 7, 'move', 10)
    else:
        result = verify_recorded_move(tmp_path, 'run', 7, 'move', 10)
        assert result['seek_frame'] == 11
        assert result['samples_before'] == result['samples_after'] == 1

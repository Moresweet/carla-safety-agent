import pytest
from carla_safety_agent.editor_events import editor_events


def record(boundary=10, **values):
    return {'execution_id':'run','command_id':'command','state':'responded',
            'observed_frame_before':boundary,'observed_frame_after':boundary,
            'response':{'ok':True},'command':{'action':'move'},**values}


def test_command_maps_strictly_after_boundary_not_to_previous_image():
    event = editor_events([record()], [10,15,20], 'run')[0]
    assert event['seek_frame']==15 and event['outcome']=='acknowledged'
    assert editor_events([record(1)], [10,15], 'run')[0]['recording_relation']=='before_recording'
    assert editor_events([record(20)], [10,15], 'run')[0]['seek_frame'] is None


@pytest.mark.parametrize('values',[{'state':'attempting'},{'response':{'ok':False}}, {'observed_frame_after':11}])
def test_uncertain_effect_does_not_claim_a_rendered_frame(values):
    event = editor_events([record(**values)],[10,15],'run')[0]
    assert event['outcome']=='uncertain' and event['seek_frame'] is None


def test_reject_mixed_execution_duplicate_commands_and_invalid_frames():
    for records, frames in [([record(execution_id='other')],[10]),([record(),record()],[10]),
                            ([record()],[10,10]),([record()],[True])]:
        with pytest.raises(ValueError): editor_events(records,frames,'run')

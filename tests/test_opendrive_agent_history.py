import pytest
from carla_safety_agent.opendrive_history import FrameIdentity
from carla_safety_agent.opendrive_agent_history import OriginalAgentQueue


def test_unmodified_original_deque_protocol():
    queue = OriginalAgentQueue()
    for step in range(42):
        queue.bind(FrameIdentity(8, step, step*.05))
        if len(queue) >= 31:
            queue.popleft()
        queue.append({'pixels': [step]})
        if step < 31:
            with pytest.raises(RuntimeError):
                queue[-1]
        else:
            assert queue[-11]['pixels'] == [step-10]
            assert queue[-1]['pixels'] == [step]
            queue[-1]['pixels'][0] = -1
    assert len(queue) == 31


def test_context_must_be_consumed_once():
    queue = OriginalAgentQueue()
    with pytest.raises(RuntimeError):
        queue.append({})
    queue.bind(FrameIdentity(1, 0, 0.))
    with pytest.raises(RuntimeError):
        queue.bind(FrameIdentity(1, 1, .05))
    queue.append({})
    with pytest.raises(RuntimeError):
        queue.append({})


def test_new_world_requires_full_agent_restart_not_just_new_images():
    queue = OriginalAgentQueue()
    queue.bind(FrameIdentity(1, 0, 0.))
    queue.append({})
    with pytest.raises(RuntimeError, match='restart agent and route'):
        queue.bind(FrameIdentity(2, 1, .05))
    assert len(queue) == 0

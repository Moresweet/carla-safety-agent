from types import SimpleNamespace as NS
import pytest
from carla_safety_agent.model_frame_context import deliver_frame_context
from carla_safety_agent.opendrive_history import FrameIdentity


def test_legacy_agent_does_not_read_world_again():
    deliver_frame_context(NS(), None, 3, {})


def test_exact_snapshot_delivered_before_preprocessing():
    received = []
    world = NS(id=7, get_snapshot=lambda: NS(frame=3, timestamp=NS(elapsed_seconds=.15)))
    deliver_frame_context(NS(set_simulator_frame=received.append), world, 3,
                          {'rgb_front': (3, object()), 'lidar': (3, object())})
    assert received == [FrameIdentity(7, 3, .15)]


@pytest.mark.parametrize('snapshot_frame, timestamp, sensors', [
    (4, .15, {'rgb': (3, None)}),
    (3, float('nan'), {'rgb': (3, None)}),
    (3, .15, {'rgb': (2, None)}),
    (3, .15, {'rgb': (True, None)}),
    (3, .15, {}),
    (3, .15, {'rgb': None}),
])
def test_bad_frame_never_reaches_model(snapshot_frame, timestamp, sensors):
    received = []
    world = NS(id=7, get_snapshot=lambda: NS(frame=snapshot_frame,
                                            timestamp=NS(elapsed_seconds=timestamp)))
    with pytest.raises(ValueError):
        deliver_frame_context(NS(set_simulator_frame=received.append), world, 3, sensors)
    assert received == []

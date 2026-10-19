import pytest

from carla_safety_agent.opendrive_history import FrameIdentity, OpenDriveHistory


def warm(history, episode=1, start=100, timestamp=5.):
    results = [history.append(FrameIdentity(episode, start+i, timestamp+i*.05))
               for i in range(32)]
    assert all(result is None for result in results[:31])
    assert results[-1] == (FrameIdentity(episode, start+21, timestamp+21*.05),
                           FrameIdentity(episode, start+31, timestamp+31*.05))


def test_original_warmup_and_half_second_history():
    history = OpenDriveHistory()
    warm(history)
    older, current = history.append(FrameIdentity(1, 132, 6.6))
    assert current.frame-older.frame == 10
    assert current.timestamp-older.timestamp == pytest.approx(.5)


@pytest.mark.parametrize('identity', [
    FrameIdentity(2, 132, 6.6),  # new world
    FrameIdentity(1, 133, 6.65),  # dropped frame
    FrameIdentity(1, 131, 6.55),  # duplicate
    FrameIdentity(1, 130, 6.5),  # stale response
    FrameIdentity(1, 132, 6.7),  # wrong cadence
])
def test_discontinuity_never_reuses_old_sweep(identity):
    history = OpenDriveHistory()
    warm(history)
    assert history.append(identity) is None
    for i in range(1, 31):
        assert history.append(FrameIdentity(identity.episode, identity.frame+i,
                                             identity.timestamp+i*.05)) is None
    result = history.append(FrameIdentity(identity.episode, identity.frame+31,
                                         identity.timestamp+31*.05))
    assert result[0].frame == identity.frame+21


@pytest.mark.parametrize('identity', [FrameIdentity(True, 1, 0.),
    FrameIdentity(1, -1, 0.), FrameIdentity(1, 1, float('nan')),
    FrameIdentity(1, 1, float('inf')), FrameIdentity(1, 1, True)])
def test_invalid_identity_clears_history(identity):
    history = OpenDriveHistory()
    warm(history)
    with pytest.raises(ValueError):
        history.append(identity)
    warm(history, start=200, timestamp=10.)


def test_payload_and_identity_are_selected_together_and_owned():
    history = OpenDriveHistory()
    payload = {'pixels': [0], 'metadata': {'frame': 0}}
    for frame in range(32):
        payload['pixels'][0] = frame
        payload['metadata']['frame'] = frame
        result = history.append_sample(FrameIdentity(1, frame, frame*.05), payload)
    payload['pixels'][0] = -1
    older, current = result
    assert older.identity.frame == older.payload['pixels'][0] == 21
    assert current.identity.frame == current.payload['metadata']['frame'] == 31
    current.payload['metadata']['frame'] = -2
    # Ten steps later, this exact current sample is the older sweep. In-place
    # edits by model preprocessing must not have corrupted the stored sample.
    for frame in range(32, 42):
        result = history.append_sample(FrameIdentity(1, frame, frame*.05), {'frame': frame})
    assert result[0].identity.frame == 31
    assert result[0].payload['metadata']['frame'] == 31
    assert len(history._frames) == 31


def test_payload_copy_failure_resets_identity_too():
    class CannotCopy:
        def __deepcopy__(self, memo):
            raise RuntimeError('copy failed')
    history = OpenDriveHistory()
    warm(history)
    with pytest.raises(RuntimeError, match='copy failed'):
        history.append_sample(FrameIdentity(1, 132, 6.6), CannotCopy())
    warm(history, start=200, timestamp=10.)


def test_world_change_discards_old_image_payloads():
    history = OpenDriveHistory()
    for episode in (10, 11):
        for frame in range(32):
            result = history.append_sample(FrameIdentity(episode, frame, frame*.05),
                                           {'world': episode, 'frame': frame})
            if frame < 31:
                assert result is None
        assert [sample.payload for sample in result] == [
            {'world': episode, 'frame': 21}, {'world': episode, 'frame': 31}]

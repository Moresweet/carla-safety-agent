"""Frame identity gate for original 20 Hz ThinkTwice/DriveAdapter adapters.

This gate does not preprocess images or infer controls. It prevents selecting
history across a dropped frame, a changed episode or an invalid clock.
"""
from collections import deque
from dataclasses import dataclass
from copy import deepcopy
import math
from typing import Any


@dataclass(frozen=True)
class FrameIdentity:
    episode: int
    frame: int
    timestamp: float


@dataclass(frozen=True)
class BoundFrame:
    identity: FrameIdentity
    payload: Any


class OpenDriveHistory:
    def __init__(self):
        self._frames = deque(maxlen=31)
        self._accepted = 0

    def reset(self):
        self._frames.clear()
        self._accepted = 0

    def append(self, identity: FrameIdentity):
        selected = self.append_sample(identity, None)
        return None if selected is None else tuple(item.identity for item in selected)

    def append_sample(self, identity: FrameIdentity, payload: Any):
        """Own a preprocessed sample and return isolated old/current snapshots.

        A single queue owns identity and data. Caller mutation, including the
        original union2one pipeline's in-place edits, cannot alter saved history.
        Payload should already be reduced by the original per-frame pipeline;
        this is not a 31-frame raw full-resolution image archive.
        """
        if (not isinstance(identity, FrameIdentity) or
                type(identity.episode) is not int or identity.episode < 0 or
                type(identity.frame) is not int or identity.frame < 0 or
                isinstance(identity.timestamp, bool) or
                not isinstance(identity.timestamp, (float, int)) or
                not math.isfinite(identity.timestamp) or identity.timestamp < 0):
            self.reset()
            raise ValueError('Invalid simulator frame identity; history cleared')
        if self._frames:
            previous = self._frames[-1].identity
            if (identity.episode != previous.episode or
                    identity.frame != previous.frame + 1 or
                    not math.isclose(identity.timestamp - previous.timestamp,
                                     0.05, rel_tol=0, abs_tol=1e-5)):
                self.reset()
        try:
            owned = deepcopy(payload)
        except Exception:
            self.reset()
            raise
        self._frames.append(BoundFrame(identity, owned))
        self._accepted += 1
        # Original agent step starts at -1 and returns without inference for
        # step < 31. Its first inference is therefore the 32nd accepted frame.
        if self._accepted < 32:
            return None
        try:
            return deepcopy((self._frames[-11], self._frames[-1]))
        except Exception:
            self.reset()
            raise

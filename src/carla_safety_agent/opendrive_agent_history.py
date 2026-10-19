"""Original-agent queue bridge; no model, calibration or controller replacement."""
import math
from copy import deepcopy

from .opendrive_history import OpenDriveHistory


class OriginalAgentQueue:
    def __init__(self):
        self.history = OpenDriveHistory()
        self.pending = None
        self.previous = None
        self.selected = None

    def bind(self, identity):
        if self.pending is not None:
            raise RuntimeError('Previous simulator frame was not consumed')
        if self.previous is not None:
            old = self.previous
            if (identity.episode != old.episode or identity.frame != old.frame+1 or
                    not math.isclose(identity.timestamp-old.timestamp, .05,
                                     rel_tol=0, abs_tol=1e-5)):
                self.history.reset()
                self.selected = None
                raise RuntimeError('Discontinuous simulator stream: restart agent and route state')
        self.pending = identity

    def __len__(self):
        return len(self.history._frames)

    def popleft(self):
        # Original run_step explicitly evicts before append. Preserve that
        # protocol while identity and payload remain in one owned queue.
        if len(self.history._frames) != 31:
            raise RuntimeError('Unexpected original-agent queue eviction')
        self.history._frames.popleft()

    def append(self, payload):
        if self.pending is None:
            raise RuntimeError('Preprocessing has no validated simulator identity')
        identity, self.pending = self.pending, None
        self.selected = None
        self.selected = self.history.append_sample(identity, payload)
        self.previous = identity

    def __getitem__(self, index):
        if self.selected is None or index not in (-11, -1):
            raise RuntimeError('Unsupported or unwarmed original history selection')
        return deepcopy(self.selected[0 if index == -11 else 1].payload)


class OriginalHistoryMixin:
    def setup(self, configuration):
        super().setup(configuration)
        if (self.data_queue_len != 31 or
                list(self.cfg['cfg']['history_query_index_lis']) != [-1, 0]):
            raise ValueError('Original model temporal configuration changed')
        self.data_queue = OriginalAgentQueue()

    def set_simulator_frame(self, identity):
        self.data_queue.bind(identity)

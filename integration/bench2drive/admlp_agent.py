"""PyTorch 2.6 compatibility shim for the official Bench2Drive AD-MLP agent."""

import torch

from carla_safety_agent.live_telemetry import publish_legacy_agent_telemetry
from team_code.admlp_b2d_agent import ADMLPAgent as _OfficialADMLPAgent


def get_entry_point():
    return "ADMLPAgent"


class ADMLPAgent(_OfficialADMLPAgent):
    """Load the verified official Lightning checkpoint with legacy pickle semantics."""

    def setup(self, path_to_conf_file):
        original_load = torch.load

        def trusted_checkpoint_load(*args, **kwargs):
            kwargs.setdefault("weights_only", False)
            return original_load(*args, **kwargs)

        torch.load = trusted_checkpoint_load
        try:
            return super().setup(path_to_conf_file)
        finally:
            torch.load = original_load

    def tick(self, input_data):
        self._telemetry_input = input_data
        self._telemetry_tick = super().tick(input_data)
        return self._telemetry_tick

    def run_step(self, input_data, timestamp):
        control = super().run_step(input_data, timestamp)
        if hasattr(self, "pid_metadata"):
            publish_legacy_agent_telemetry(
                frame=self.step, input_data=self._telemetry_input,
                tick=self._telemetry_tick, control=control,
                controller=self.pid_metadata, model="AD-MLP",
                camera_ids=("CAM_FRONT",))
        return control

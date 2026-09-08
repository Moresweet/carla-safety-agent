"""Telemetry-enabled wrapper for the official Bench2Drive VAD agent."""

from carla_safety_agent.live_telemetry import publish_driving_telemetry
from team_code.vad_b2d_agent import VadAgent as _OfficialVADAgent


def get_entry_point():
    return "VadAgent"


class VadAgent(_OfficialVADAgent):
    def tick(self, input_data):
        self._telemetry_tick = super().tick(input_data)
        return self._telemetry_tick

    def run_step(self, input_data, timestamp):
        control = super().run_step(input_data, timestamp)
        metadata = getattr(self, "pid_metadata", None)
        if metadata and metadata.get("plan") is not None:
            publish_driving_telemetry(
                frame=self.step, tick=self._telemetry_tick,
                plan=metadata["plan"], control=control,
                controller=metadata, model="VAD")
        return control

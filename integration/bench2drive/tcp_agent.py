"""Telemetry-enabled wrapper for the official Bench2Drive TCP agent."""

from carla_safety_agent.live_telemetry import publish_legacy_agent_telemetry
from team_code.tcp_b2d_agent import TCPAgent as _OfficialTCPAgent


def get_entry_point():
    return "TCPAgent"


class TCPAgent(_OfficialTCPAgent):
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
                controller=self.pid_metadata, model="TCP",
                camera_ids=("CAM_FRONT", "CAM_FRONT_LEFT", "CAM_FRONT_RIGHT"))
        return control

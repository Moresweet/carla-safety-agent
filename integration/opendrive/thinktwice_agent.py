"""Development-only original ThinkTwice wrapper; not a catalog-ready adapter.

Requires the isolated original model environment and its team_code on sys.path.
Real sensor inference and closed-loop acceptance are still required.
"""
from carla_safety_agent.opendrive_agent_history import OriginalHistoryMixin
from team_code.thinktwice_agent import ThinkTwiceAgent as OriginalThinkTwiceAgent
from team_code import thinktwice_agent as original_module
from carla_safety_agent.strict_model_weights import load_complete_checkpoint
from copy import deepcopy
from carla_safety_agent.opendrive_sensor_profile import original_sensor_specs
from unittest.mock import patch


def get_entry_point():
    return 'ThinkTwiceAgent'


class ThinkTwiceAgent(OriginalHistoryMixin, OriginalThinkTwiceAgent):
    def sensors(self):
        return original_sensor_specs(super().sensors())

    def setup(self, configuration):
        original_build = original_module.build_model

        def build_full_checkpoint_model(config, **kwargs):
            config = deepcopy(config)
            config.img_encoder.img_backbone_conf.init_cfg = None
            return original_build(config, **kwargs)

        # Original agent imports these symbols into its module. Limit overrides
        # to setup, restore on any failure, and retain its original pipelines.
        with patch.object(original_module, 'build_model', build_full_checkpoint_model), \
                patch.object(original_module, 'load_checkpoint', load_complete_checkpoint):
            super().setup(configuration)

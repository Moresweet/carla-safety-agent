"""Development-only DriveAdapter wrapper; public execution remains disabled."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from carla_safety_agent.opendrive_agent_history import OriginalHistoryMixin
from carla_safety_agent.opendrive_sensor_profile import original_sensor_specs
from carla_safety_agent.strict_model_weights import load_complete_checkpoint
from team_code.driveadapter_agent import DriveAdapterAgent as OriginalDriveAdapterAgent
from team_code import driveadapter_agent as original_module


def get_entry_point():
    return 'DriveAdapterAgent'


class DriveAdapterAgent(OriginalHistoryMixin, OriginalDriveAdapterAgent):
    def tick(self, input_data):
        self._planning_navigation_reference = None
        result = super().tick(input_data)
        # Observe the original preprocessing outputs, not a second GPS filter.
        # Store compass before its original run_step NaN handling / pi/2 shift.
        self._planning_navigation_reference = {
            'schema_version': 'driveadapter-navigation-observation/2',
            'model_step': self.step,
            'world_xy_m': [float(result['y']), -float(result['x'])],
            'compass_rad': float(result['theta']),
            'source': 'original_tick_smoothed_gps',
            'coordinate_frame': 'original_route_planner_xy_not_carla_world',
            'gps_mean_lat_lon': [float(x) for x in self._route_planner.mean],
            'gps_scale_lat_lon': [float(x) for x in self._route_planner.scale],
        }
        return result

    def set_native_ego(self, ego):
        if ego is None or not ego.is_alive:
            raise ValueError('DriveAdapter requires the live execution-owned ego')
        self._native_ego = ego

    def set_native_global_plan(self, world, gps_plan, world_plan):
        road_map = world.get_map()
        route = [(road_map.get_waypoint(transform.location, project_to_road=True), command)
                 for transform, command in world_plan]
        if not route or any(waypoint is None for waypoint, _ in route):
            raise ValueError('DriveAdapter requires a valid native waypoint route')
        self.set_global_plan(gps_plan, world_plan, route)

    def _init(self):
        from srunner.scenariomanager.carla_data_provider import CarlaDataProvider
        # Native actors are not in the benchmark provider's actor pool. Bind
        # the execution-owned vehicle explicitly, never scan for another hero.
        ego = getattr(self, '_native_ego', None)
        if ego is None or not ego.is_alive:
            raise ValueError('Native ego is unavailable before model initialization')
        with patch.object(CarlaDataProvider, 'get_ego', lambda: ego, create=True):
            super()._init()

    def destroy(self):
        if hasattr(self, 'model'):
            super().destroy()

    def sensors(self):
        return original_sensor_specs(super().sensors())

    def setup(self, configuration):
        original_build = original_module.build_model
        original_numpy_load = original_module.np.load
        root = Path(original_module.__file__).resolve().parents[2]

        def load_mask(filename, *args, **kwargs):
            # Resolve only the original relative asset; do not change cwd.
            if str(filename) == 'open_loop_training/ev_mask.npy':
                filename = root / filename
            return original_numpy_load(filename, *args, **kwargs)

        def build_full_model(config, **kwargs):
            from open_loop_training.code.model_code.dense_heads.driver_adapter_head import DriveAdapterHead
            config = deepcopy(config)
            config.img_encoder.img_backbone_conf.init_cfg = None
            # Mandatory full weights follow; never unpickle ancillary Gym data.
            with patch.object(DriveAdapterHead, 'load_roach_layers', lambda self, modules: None):
                return original_build(config, **kwargs)

        def load_weights(model, filename, **kwargs):
            return load_complete_checkpoint(model, filename, legacy_sparse_rsck=True, **kwargs)

        with patch.object(original_module, 'build_model', build_full_model), \
                patch.object(original_module, 'load_checkpoint', load_weights), \
                patch.object(original_module.np, 'load', load_mask):
            super().setup(configuration)

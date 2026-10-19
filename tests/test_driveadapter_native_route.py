import ast
from pathlib import Path
from types import SimpleNamespace as NS

import pytest


def adapter_class():
    source = Path(__file__).resolve().parents[1] / 'integration/opendrive/driveadapter_agent.py'
    node = next(n for n in ast.parse(source.read_text()).body
                if isinstance(n, ast.ClassDef) and n.name == 'DriveAdapterAgent')
    class Base:
        def tick(self, inputs):
            self.step += 1
            return inputs
        def set_global_plan(self, *args): self.received = args
        def destroy(self): del self.model
    env = {'OriginalHistoryMixin': type('Mixin', (), {}), 'OriginalDriveAdapterAgent': Base}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), 'exec'), env)
    return env['DriveAdapterAgent']


def test_tick_observes_original_navigation_without_changing_return_value():
    adapter=adapter_class()(); adapter.step=4
    adapter._route_planner=NS(mean=[0.,0.],scale=[100.,200.])
    inputs={'x':20.,'y':10.,'theta':1.2}
    assert adapter.tick(inputs) is inputs
    assert adapter._planning_navigation_reference=={
        'schema_version':'driveadapter-navigation-observation/2',
        'model_step':5,'world_xy_m':[10.,-20.],'compass_rad':1.2,
        'source':'original_tick_smoothed_gps',
        'coordinate_frame':'original_route_planner_xy_not_carla_world',
        'gps_mean_lat_lon':[0.,0.],'gps_scale_lat_lon':[100.,200.]}
    inputs['x']=999
    adapter._route_planner.scale[0]=999
    assert adapter._planning_navigation_reference['gps_scale_lat_lon']==[100.,200.]
    assert adapter._planning_navigation_reference['world_xy_m']==[10.,-20.]


def test_native_waypoints_keep_route_order_commands_and_original_plans():
    adapter = adapter_class()()
    gps = [{'lat': 1}, {'lat': 2}]
    plan = [(NS(location='a'), 'left'), (NS(location='b'), 'right')]
    def waypoint(location, project_to_road):
        assert project_to_road is True
        return 'wp-' + location
    adapter.set_native_global_plan(NS(get_map=lambda: NS(get_waypoint=waypoint)), gps, plan)
    assert adapter.received == (gps, plan, [('wp-a', 'left'), ('wp-b', 'right')])
    assert adapter.received[0] is gps and adapter.received[1] is plan


@pytest.mark.parametrize('plan', [[], [(NS(location='missing'), 'straight')]])
def test_missing_native_route_is_rejected_before_original_agent(plan):
    adapter = adapter_class()()
    world = NS(get_map=lambda: NS(get_waypoint=lambda *a, **kw: None))
    with pytest.raises(ValueError, match='valid native waypoint route'):
        adapter.set_native_global_plan(world, [], plan)
    assert not hasattr(adapter, 'received')


def test_destroy_handles_partial_setup_and_repeated_cleanup():
    adapter = adapter_class()()
    adapter.destroy()
    adapter.model = object()
    adapter.destroy()
    adapter.destroy()
    assert not hasattr(adapter, 'model')


def test_explicit_ego_binding_rejects_missing_or_dead_actor():
    adapter = adapter_class()()
    for ego in (None, NS(is_alive=False)):
        with pytest.raises(ValueError, match='live execution-owned ego'):
            adapter.set_native_ego(ego)
    ego = NS(is_alive=True, id=123)
    adapter.set_native_ego(ego)
    assert adapter._native_ego is ego

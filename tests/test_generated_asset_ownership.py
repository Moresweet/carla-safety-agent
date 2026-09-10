from types import SimpleNamespace as NS

import pytest

from carla_safety_agent.carla_adapter import CarlaAdapter
from carla_safety_agent.owned_resources import OwnedActors


class Vector:
    def __add__(self, other): return self
    def __mul__(self, other): return self


class Blueprint:
    def __iter__(self):
        return iter(NS(id=k) for k in ('mesh_path','mass','scale_x','scale_y','scale_z'))
    def set_attribute(self, *args): pass


@pytest.mark.parametrize('shape', ['metal_pipes', 'concrete_barriers'])
@pytest.mark.parametrize('failure', ['second_spawn', 'journal', 'road_end'])
def test_partial_generated_assets_stay_with_parent_cleanup(shape, failure):
    calls=[]
    actor=NS(id=1,type_id='static.prop.mesh',destroy=lambda:pytest.fail('Parent owns cleanup'))
    transform=NS(location=Vector(),get_right_vector=lambda:Vector(),rotation=NS(pitch=0,yaw=0,roll=0))
    def next_waypoint(distance):
        return [] if failure=='road_end' and distance>10 else [NS(transform=transform)]
    def spawn(*args):
        calls.append('spawn')
        return actor if len(calls)==1 else None
    world=NS(get_blueprint_library=lambda:NS(find=lambda _:Blueprint()),
             get_map=lambda:NS(get_waypoint=lambda *a,**kw:NS(next=next_waypoint)),
             try_spawn_actor=spawn)
    carla=NS(Transform=lambda *args:None,Location=lambda **kw:Vector(),Rotation=lambda **kw:None)
    spec=NS(shape=shape,dimensions_m=(2,1,1),mass_kg=100,count=2,distance_ahead_m=10,lateral_offset_m=0)
    def register(_):
        if failure=='journal': raise OSError('disk full')
    owned=OwnedActors(NS(register=register))
    with pytest.raises((RuntimeError,OSError)):
        CarlaAdapter._spawn_generated_asset(carla,world,NS(get_location=lambda:None),spec,owned)
    assert owned==[actor], 'Parent must retain partial creations even if durable registration fails'


def test_background_vehicle_is_owned_before_control_raises():
    actor=NS(id=1)
    def control(*args): raise RuntimeError('control failed')
    actor.apply_control=control
    transform=NS(location=Vector(),get_right_vector=lambda:Vector())
    world=NS(get_blueprint_library=lambda:NS(filter=lambda _: [NS(id='test')]),
             try_spawn_actor=lambda *args:actor)
    owned=[]
    with pytest.raises(RuntimeError,match='control failed'):
        CarlaAdapter._spawn_background_road_users(NS(VehicleControl=lambda **kw:None),world,
            NS(next=lambda _:[NS(transform=transform)]),NS(traffic_vehicle_count=1,pedestrian_count=0),None,owned)
    assert owned==[actor]

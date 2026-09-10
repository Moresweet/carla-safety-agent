from types import SimpleNamespace as NS
import pytest
from carla_safety_agent.batch_textures import texture_records, overlay_materials, require_texture_world


def edit(target='house', digest='a'):
    return {'target': target, 'component': 'mesh', 'slot': 0, 'texture': digest*64}


def test_overlay_preserves_unrelated_user_edits_and_inputs():
    before = [edit(), edit('road')]
    variant = {'environment_materials': [edit(digest='b')]}
    assert overlay_materials(before, variant) == [edit(digest='b'), edit('road')]
    assert before == [edit(), edit('road')]
    assert overlay_materials(before, {}) == before


@pytest.mark.parametrize('config', [None, [], False, {'command': 'x'},
    {'environment_materials': [edit(), edit()]},
    {'environment_materials': [{**edit(), 'texture': 'bad'}]},
    {'environment_materials': [{**edit(), 'slot': True}]}])
def test_invalid_configuration_fails_closed(config):
    with pytest.raises(ValueError): texture_records(config)


@pytest.mark.parametrize('map_name,generated,sync', [('Town05', None, False),
    ('Town04', {'segments': []}, False), ('Town04', None, True)])
def test_texture_world_refuses_switch_or_another_owner(map_name, generated, sync):
    world = NS(get_map=lambda:NS(name='/Game/Carla/Maps/Town04'),
               get_settings=lambda:NS(synchronous_mode=sync))
    with pytest.raises(ValueError): require_texture_world(world, {'map_name':map_name,'generated_map':generated})


def test_current_map_is_allowed():
    world = NS(get_map=lambda:NS(name='/Game/Carla/Maps/Town04'),
               get_settings=lambda:NS(synchronous_mode=False))
    require_texture_world(world, {'map_name':'Town04'})

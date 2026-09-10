import pytest
from carla_safety_agent.asset_search import search_assets


def test_complete_catalog_search_is_not_limited_to_first_200():
    ids = [f'static.prop.asset{i:04}' for i in range(300)] + ['generated.prop.zz_barrier']
    assert search_assets(ids, '护栏')['blueprints'] == ['generated.prop.zz_barrier']
    pages = [search_assets(ids, offset=i, limit=48)['blueprints'] for i in range(0, 301, 48)]
    assert sum(pages, []) == sorted(ids)
    assert not search_assets(ids, offset=288)['has_more']


def test_keywords_and_category_are_combined_without_inventing_assets():
    ids = ['vehicle.audi.a2', 'vehicle.tesla.model3', 'static.prop.streetbarrier',
           'generated.prop.barrier', 'walker.pedestrian.0001', 'sensor.camera.rgb']
    assert search_assets(ids, '车辆 奥迪')['blueprints'] == ['vehicle.audi.a2']
    assert search_assets(ids, '护栏', kind='generated')['blueprints'] == ['generated.prop.barrier']
    assert search_assets(ids, '护栏', kind='vehicle')['total'] == 0
    assert search_assets(ids, '蓝色')['total'] == 0
    assert search_assets(ids + ids)['total'] == 5


@pytest.mark.parametrize('kwargs', [{'offset': -1}, {'offset': True}, {'limit': 201},
    {'limit': 0}, {'kind': 'flying'}, {'query': 'x'*257}, {'query': None}])
def test_invalid_search_parameters(kwargs):
    with pytest.raises(ValueError):
        search_assets([], **kwargs)

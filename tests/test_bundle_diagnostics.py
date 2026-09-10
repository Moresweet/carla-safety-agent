import json
import pytest
from types import SimpleNamespace

from carla_safety_agent.bundle_diagnostics import diagnose


@pytest.mark.parametrize('listed_map', ['/Game/Carla/Maps/Town04', 'Town04'])
def test_dependency_observations_do_not_switch_maps(tmp_path, listed_map):
    world = SimpleNamespace(get_map=lambda: SimpleNamespace(name='Carla/Maps/Town04'),
                            get_blueprint_library=lambda: [SimpleNamespace(id='static.prop.box')],
                            get_names_of_all_objects=lambda: ['building'])
    client = SimpleNamespace(get_world=lambda: world,
                             get_available_maps=lambda: [listed_map, '/Game/Carla/Maps/Town05'])
    folder = tmp_path/'material-exports/Town04'; folder.mkdir(parents=True)
    (folder/'preview-catalog.json').write_text(json.dumps({'actors': {'building': [
        {'component': 'mesh', 'slots': [{'slot': 0, 'status': 'uv0_ready', 'mesh_file': 'mesh.json'}]}]}}))
    (folder/'mesh.json').write_text(json.dumps({'triangleCount': 1, 'vertices': [0.0]*15}))
    manifest = {'dependencies': {'maps': ['Carla/Maps/Town04', 'Carla/Maps/Town99'],
        'blueprints': ['static.prop.box', 'missing'], 'material_slots': [
            ['Carla/Maps/Town04', 'building', 'mesh', 0],
            ['Carla/Maps/Town04', 'building', 'mesh', 1],
            ['Carla/Maps/Town05', 'building', 'mesh', 0]]}}
    result = diagnose(manifest, client, tmp_path)
    assert [c['state'] for c in result['checks']] == ['available', 'missing', 'available', 'missing',
                                                    'available', 'missing', 'not_checked']
    assert not result['all_declared_dependencies_available']
    assert not result['live_world_modified'] and not result['restore_verified']
    (folder/'mesh.json').unlink()
    assert diagnose(manifest, client, tmp_path)['checks'][4]['state'] == 'missing'


def test_generated_source_is_not_runtime_availability(tmp_path):
    world = SimpleNamespace(get_map=lambda: SimpleNamespace(name='Town04'),
                            get_blueprint_library=lambda: [], get_names_of_all_objects=lambda: [])
    client = SimpleNamespace(get_world=lambda:world, get_available_maps=lambda:['Town04'])
    blueprint = 'generated.prop.barrier'
    manifest = {'dependencies':{'maps':['Town04'], 'blueprints':[blueprint], 'material_slots':[],
                                'generated_asset_sources':{blueprint:'a'*64}}}
    result = diagnose(manifest, client, tmp_path)
    assert result['checks'][1]['state'] == 'not_checked'
    assert result['checks'][1]['source_package_included']
    assert not result['all_declared_dependencies_available']


def test_model_reference_does_not_claim_installed_or_executed(tmp_path):
    world=SimpleNamespace(get_map=lambda:SimpleNamespace(name='Town04'),
                          get_blueprint_library=lambda:[],get_names_of_all_objects=lambda:[])
    client=SimpleNamespace(get_world=lambda:world,get_available_maps=lambda:['Town04'])
    result=diagnose({'dependencies':{'maps':['Town04'],'blueprints':[],'material_slots':[],
                                    'model_ids':['vad']}},client,tmp_path)
    assert result['checks'][-1]['state']=='not_checked'
    assert not result['all_declared_dependencies_available']

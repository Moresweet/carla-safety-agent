"""Materialize scenario-affecting matrix axes before execution preflight."""
import hashlib
import json
from .experiment_matrix import canonical, compile_matrix
from .io import scenario_from_dict
from .scenario_archive import archive_scenario
from .batch_textures import texture_records


def materialize_scenario(root, job):
    configuration = job['configuration']
    texture_records(configuration['textures']['configuration'])
    # Validate this combination using the same matrix contract and identity.
    single = compile_matrix({k: [v] for k, v in configuration.items()})['jobs'][0]
    if single['job_id'] != job['job_id']:
        raise ValueError('Matrix job configuration identity mismatch')
    scene = configuration['scenes']['configuration']
    if set(scene) != {'scenario', 'scenario_sha256'}:
        raise ValueError('Scene variant requires a full scenario and canonical SHA-256')
    payload = canonical(scene['scenario'])
    if hashlib.sha256(payload).hexdigest() != scene['scenario_sha256']:
        raise ValueError('Matrix source scenario checksum mismatch')
    scenario = json.loads(payload)
    scenario_from_dict(scenario)
    weather = configuration['weather']['configuration']
    limits = {'cloudiness': (0, 100), 'precipitation': (0, 100),
              'fog_density': (0, 100), 'sun_altitude_angle': (-90, 90)}
    if set(weather)-set(limits):
        raise ValueError('Unsupported batch weather field')
    for key, value in weather.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not limits[key][0] <= value <= limits[key][1]:
            raise ValueError('Invalid batch weather value')
    scenario['environment'].update(weather)
    scenario['seed'] = configuration['seeds']
    scenario['scenario_id'] = 'batch-'+job['job_id']
    provenance = scenario.setdefault('provenance', {})
    provenance['experiment_matrix'] = {'job_id': job['job_id'],
        'source_scenario_sha256': scene['scenario_sha256'],
        'variant_ids': {k: configuration[k]['id'] for k in ('scenes', 'models', 'weather', 'textures')}}
    provenance['experiment_matrix']['texture_configuration'] = configuration['textures']['configuration']
    scenario_from_dict(scenario)
    path, digest = archive_scenario(root, scenario)
    return {'scenario_path': str(path), 'scenario_sha256': digest,
            'scenario': scenario, 'model_configuration': configuration['models']['configuration'],
            'texture_configuration': configuration['textures']['configuration'],
            'execution_ready': False}

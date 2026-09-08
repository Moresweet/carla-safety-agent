"""One registry for supported batch adapters and user-visible capabilities."""
from .experiment_matrix import MAX_JOBS

MODEL_IDS = ('uniad-tiny', 'uniad-base', 'vad', 'tcp', 'admlp')


def supported_configuration(configuration):
    return configuration == {'action': 'rule-run'} or any(
        configuration == {'action': 'run', 'algorithm': model} for model in MODEL_IDS)


def batch_capabilities(algorithms):
    installed = {item['id']: item for item in algorithms}
    models = [{'id': 'rule-run', 'name': '规则驾驶', 'configuration': {'action': 'rule-run'},
               'adapter_supported': True, 'dependencies_available': None}]
    for model in MODEL_IDS:
        entry = installed.get(model, {})
        models.append({'id': model, 'name': entry.get('name', model),
                       'configuration': {'action': 'run', 'algorithm': model},
                       'adapter_supported': True,
                       'dependencies_available': entry.get('status') == 'available'})
    return {'models': models, 'max_jobs': MAX_JOBS, 'texture_variants_supported': False,
            'unified_capture': True, 'background_scheduler': True,
            'preflight_required': True,
            'limitations': ['Installed model files are not proof of current simulator readiness',
                            'Texture configuration must be empty',
                            'No automatic failed-job retry']}

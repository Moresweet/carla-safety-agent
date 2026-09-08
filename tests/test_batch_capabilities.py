from carla_safety_agent.batch_capabilities import batch_capabilities, supported_configuration


def test_capabilities_share_dispatch_registry_and_keep_readiness_separate():
    result = batch_capabilities([{'id': 'vad', 'name': 'VAD', 'status': 'available'},
                                 {'id': 'tcp', 'status': 'missing_checkpoint'},
                                 {'id': 'unknown', 'status': 'available'}])
    assert len(result['models']) == 6
    assert all(supported_configuration(item['configuration']) for item in result['models'])
    models = {item['id']: item for item in result['models']}
    assert models['vad']['dependencies_available'] is True
    assert models['tcp']['dependencies_available'] is False
    assert models['uniad-base']['dependencies_available'] is False
    assert models['rule-run']['dependencies_available'] is None
    assert result['preflight_required'] is True
    assert result['texture_variants_supported'] is False
    assert not supported_configuration({'action': 'run', 'algorithm': 'unknown'})
    assert not supported_configuration({'action': 'run', 'algorithm': 'vad', 'command': 'extra'})

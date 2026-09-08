import json
import pytest
from carla_safety_agent.capture_identity import verify_capture_identity
from carla_safety_agent.scenario_archive import archive_scenario


def test_capture_matches_execution_and_rejects_wrong_scenario(tmp_path):
    path, digest = archive_scenario(tmp_path, {'scenario_id': 'scene', 'seed': 31})
    execution = {'run_id': 'execution', 'configuration': {'scenario_sha256': digest}}
    manifest = {'execution_id': 'execution', 'scenario_id': 'scene',
                'scenario': {'path': path.name, 'sha256': digest, 'scenario_id': 'scene'}}
    def save(): (tmp_path/'manifest.json').write_text(json.dumps(manifest))
    save()
    assert verify_capture_identity(tmp_path, execution)['scenario_sha256'] == digest
    manifest['scenario']['sha256'] = '0'*64; save()
    with pytest.raises(ValueError, match='differs'): verify_capture_identity(tmp_path, execution)
    manifest['scenario']['sha256'] = digest
    manifest['scenario']['path'] = '../'+path.name; save()
    with pytest.raises(ValueError, match='path'): verify_capture_identity(tmp_path, execution)
    manifest['scenario']['path'] = path.name
    manifest['execution_id'] = 'other'; save()
    with pytest.raises(ValueError, match='execution'): verify_capture_identity(tmp_path, execution)
    manifest['execution_id'] = 'execution'; save()
    path.write_text('{}')
    with pytest.raises(ValueError): verify_capture_identity(tmp_path, execution)

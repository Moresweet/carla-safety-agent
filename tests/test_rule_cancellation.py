import pytest
from carla_safety_agent.carla_adapter import CarlaAdapter, RuleRunCancelled


def test_prestart_cancel_does_not_connect_or_create_output(tmp_path, monkeypatch):
    adapter = CarlaAdapter()
    def forbidden():
        pytest.fail('Cancellation must be checked before CARLA import/connection')
    monkeypatch.setattr(adapter, '_module', forbidden)
    output = tmp_path/'must-not-exist'
    with pytest.raises(RuleRunCancelled, match='before startup'):
        adapter.run(None, output, should_stop=lambda: True)
    assert not output.exists()

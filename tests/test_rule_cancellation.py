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


def test_editor_commands_precede_tick_and_capture():
    import ast
    import inspect
    import textwrap
    tree = ast.parse(textwrap.dedent(inspect.getsource(CarlaAdapter.run)))
    loop = next(node for node in ast.walk(tree) if isinstance(node, ast.For)
                and isinstance(node.target, ast.Name) and node.target.id == 'frame')
    calls = [node for node in ast.walk(loop) if isinstance(node, ast.Call)]
    editor = next(node for node in calls if isinstance(node.func, ast.Name)
                  and node.func.id == 'on_frame')
    tick = next(node for node in calls if isinstance(node.func, ast.Attribute)
                and node.func.attr == 'tick')
    capture = next(node for node in calls if isinstance(node.func, ast.Attribute)
                   and node.func.attr == 'process_frame')
    assert editor.lineno < tick.lineno < capture.lineno

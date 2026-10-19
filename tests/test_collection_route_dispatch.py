"""Prevent recording controls being shadowed by manual driving dispatch."""
import ast
from pathlib import Path


def test_recording_and_manual_control_have_distinct_reachable_handlers():
    source = Path(__file__).resolve().parents[1]/'tools/livery_bridge.py'
    tree = ast.parse(source.read_text())
    post = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name=='do_POST')
    for route, handler in (('/collection/control','manual_sensor_control'),
                           ('/collection/recording','recording_control')):
        branches = [node for node in ast.walk(post) if isinstance(node,ast.If)
                    and isinstance(node.test,ast.Compare) and len(node.test.ops)==1
                    and isinstance(node.test.ops[0],ast.Eq)
                    and isinstance(node.test.comparators[0],ast.Constant)
                    and node.test.comparators[0].value==route]
        assert len(branches)==1, f'{route} must have exactly one dispatch branch'
        calls = [node.func.id for statement in branches[0].body for node in ast.walk(statement)
                 if isinstance(node,ast.Call) and isinstance(node.func,ast.Name)]
        assert handler in calls
    ui = (source.parents[0]/'livery-designer/app/recordingControl.ts').read_text()
    assert "'/collection/recording'" in ui
    assert "'/collection/control'" not in ui

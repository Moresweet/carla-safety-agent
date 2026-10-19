import ast
import io
import json
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import pytest


@pytest.mark.parametrize('query', ['', '?path=/tmp', '?unknown='])
def test_bridge_runtime_inventory_fixed_root(tmp_path, query):
    runtime = tmp_path/'.runtime'
    runtime.mkdir()
    original = runtime/'bridge.log'
    original.write_bytes(b'keep log')
    source = Path(__file__).resolve().parents[1]/'tools/livery_bridge.py'
    handler_node = next(node for node in ast.parse(source.read_text()).body
                        if isinstance(node, ast.ClassDef) and node.name == 'Handler')
    env = dict(BaseHTTPRequestHandler=object, urlparse=urlparse, parse_qs=parse_qs,
               json=json, PROJECT_ROOT=tmp_path)
    exec(compile(ast.Module(body=[handler_node], type_ignores=[]), str(source), 'exec'), env)
    handler = env['Handler']()
    handler.path = '/system/runtime-storage'+query
    handler.wfile = io.BytesIO()
    statuses = []
    handler._headers = lambda status=200: statuses.append(status)
    handler.do_GET()
    result = json.loads(handler.wfile.getvalue())
    assert statuses == [400 if query else 200]
    if not query:
        assert result['root'] == str(runtime)
        assert result['categories'][0]['name'] == 'bridge.log'
        assert result['deletion_approved'] is False
    assert original.read_bytes() == b'keep log'
    assert list(runtime.iterdir()) == [original]

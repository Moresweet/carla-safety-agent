"""Exercise the real Handler AST without importing native CARLA or starting threads."""
import ast
import io
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest


@pytest.mark.parametrize('error', [None, ValueError('World changed while waiting'), RuntimeError('RPC timeout')])
def test_scene_state_resolves_before_http_headers(error):
    path = Path(__file__).resolve().parents[1] / 'tools/livery_bridge.py'
    node = next(n for n in ast.parse(path.read_text()).body if isinstance(n, ast.ClassDef) and n.name == 'Handler')
    events = []
    def scene_state():
        events.append('read')
        if error:
            raise error
        return {'ok': True, 'map': 'Town04'}
    env = {'BaseHTTPRequestHandler': object, 'urlparse': urlparse, 'parse_qs': parse_qs,
           'json': json, 'scene_state': scene_state}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), env)
    handler = env['Handler']()
    handler.path = '/scene/state'
    handler.wfile = io.BytesIO()
    handler._headers = lambda status=200: events.append(status)
    handler.do_GET()
    assert events == ['read', 503 if error else 200]
    payload = json.loads(handler.wfile.getvalue())
    assert payload['ok'] is (error is None)
    if error:
        assert payload['retryable'] is True
    class Disconnected:
        def write(self, _payload):
            raise BrokenPipeError('page closed')
    events.clear()
    handler.wfile = Disconnected()
    handler.do_GET()
    assert events == ['read', 503 if error else 200]

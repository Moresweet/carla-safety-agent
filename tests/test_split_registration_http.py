"""Real bridge HTTP handler, isolated storage, no native simulator imports."""
import ast
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from urllib.parse import urlparse

import pytest
from carla_safety_agent.dataset_split import verified_split
from carla_safety_agent.split_registry import registered_split_references, registry_mutation_lock


def test_split_upload_over_http(tmp_path):
    captures = tmp_path/'captures'
    run = captures/'capture-http'; run.mkdir(parents=True)
    (run/'manifest.json').write_text(json.dumps({'run_id':run.name,'status':'saved','frame_count':1}))
    (run/'index.json').write_text('{"frames":[{"frame":1,"timestamp":0.05}]}')
    document = verified_split([{'run_id':run.name,'scene_group':'explicit-http-fixture'}], captures)
    source = Path(__file__).resolve().parents[1]/'tools/livery_bridge.py'
    node = next(n for n in ast.parse(source.read_text()).body if isinstance(n,ast.ClassDef) and n.name=='Handler')
    env = dict(BaseHTTPRequestHandler=BaseHTTPRequestHandler, urlparse=urlparse,
               json=json, PROJECT_ROOT=tmp_path, DATASET_ROOT=captures, FRONTEND_ORIGIN='http://localhost:3000')
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(source),'exec'),env)
    try:
        server = ThreadingHTTPServer(('127.0.0.1',0),env['Handler'])
    except PermissionError:
        pytest.skip('Local listening socket requires approved network execution')
    thread = threading.Thread(target=server.serve_forever,daemon=True); thread.start()
    def post(payload):
        connection = http.client.HTTPConnection(*server.server_address,timeout=5)
        try:
            connection.request('POST','/datasets/splits/register',payload,{'Content-Type':'application/json'})
            response = connection.getresponse()
            return response.status,json.loads(response.read())
        finally: connection.close()
    try:
        payload = json.dumps(document).encode()
        status, first = post(payload)
        assert status==200 and first['ok'] and first['created']
        status, second = post(payload)
        assert status==200 and not second['created'] and second['sha256']==first['sha256']
        for invalid in (b'{',b'{"path":"/etc/passwd"}',b'{"a":1,"a":2}',b'null',b'[]',b'{"overflow":1e999}',b'['*2000+b']'*2000):
            status,result = post(invalid)
            assert status==400 and not result['ok']
        with registry_mutation_lock(tmp_path/'data/dataset-splits'):
            status,result = post(payload)
            assert status==409 and not result['ok']
        connection = http.client.HTTPConnection(*server.server_address,timeout=5)
        try:
            connection.putrequest('POST','/datasets/splits/register')
            connection.putheader('Content-Length',str(8*1024**2+1))
            connection.endheaders()  # No body: rejection must precede body read.
            response = connection.getresponse()
            assert response.status==413 and not json.loads(response.read())['ok']
        finally: connection.close()
        stored = Path(first['path']); registered_bytes = stored.read_bytes()
        (run/'index.json').write_text('{"frames":[{"frame":2,"timestamp":0.1}]}')
        status,result = post(payload)
        assert status==400 and not result['ok']
        assert stored.read_bytes()==registered_bytes
        refs = registered_split_references(tmp_path/'data/dataset-splits')
        assert refs['complete'] and refs['scanned_files']==1 and refs['references'][run.name]
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)

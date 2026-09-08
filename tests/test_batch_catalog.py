import pytest
from carla_safety_agent.batch_catalog import BatchCatalog


def dimensions():
    return {**{a: [{'id': 'base', 'configuration': {}}] for a in ('scenes','models','weather','textures')}, 'seeds': [1]}


def test_catalog_create_read_and_paginate_without_dispatch(tmp_path):
    c = BatchCatalog(tmp_path/'batches')
    first, second = c.create(dimensions()), c.create(dimensions())
    assert first['batch_id'] != second['batch_id']
    assert first['dispatched'] is False
    page = c.list(limit=1)
    assert len(page['batches']) == 1 and page['next_cursor']
    next_page = c.list(limit=1, after=page['next_cursor'])
    assert len(next_page['batches']) == 1 and next_page['next_cursor'] is None
    assert c.read(first['batch_id'])['jobs'][0]['state'] == 'pending'
    with pytest.raises(ValueError): c.read('../outside')


def test_catalog_corruption_visible_and_symlink_refused(tmp_path):
    c = BatchCatalog(tmp_path/'batches'); item = c.create(dimensions())
    path = c.directory(item['batch_id'])/'queue.json'
    path.write_text('{}')
    assert c.list()['batches'][0]['error']
    (c.root/'linked').symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError): c.read('linked')


def test_expanded_plan_rejected_before_catalog_creation(tmp_path, monkeypatch):
    import carla_safety_agent.experiment_matrix as matrix
    monkeypatch.setattr(matrix, 'MAX_PLAN_BYTES', 1024)
    data = dimensions()
    data['scenes'][0]['configuration'] = {'description': 'x'*200}
    data['seeds'] = list(range(10))
    catalog = BatchCatalog(tmp_path/'batches')
    with pytest.raises(ValueError, match='Expanded'):
        catalog.create(data)
    assert not catalog.root.exists()


def test_batch_http_create_list_report_and_invalid_id(tmp_path):
    import ast
    import io
    import json
    from pathlib import Path
    from urllib.parse import urlparse, parse_qs
    from carla_safety_agent.experiment_report import summarize_queue, compare_variants
    from carla_safety_agent.batch_control import control_batch
    from carla_safety_agent.batch_capabilities import batch_capabilities
    source = Path(__file__).resolve().parents[1]/'tools/livery_bridge.py'
    node = next(n for n in ast.parse(source.read_text()).body
                if isinstance(n, ast.ClassDef) and n.name == 'Handler')
    catalog = BatchCatalog(tmp_path/'batches')
    env = {'BaseHTTPRequestHandler': object, 'urlparse': urlparse, 'parse_qs': parse_qs,
           'json': json, 'BATCHES': catalog, 'PROJECT_ROOT': tmp_path,
           'summarize_queue': summarize_queue, 'compare_variants': compare_variants}
    env.update(batch_capabilities=batch_capabilities, BENCH2DRIVE_ZOO=tmp_path,
               BENCH2DRIVE_TCP_ZOO=tmp_path,
               algorithm_catalog=lambda *args: [{'id': 'vad', 'status': 'available'}])
    env['batch_control'] = lambda data: control_batch(
        catalog, data, None, tmp_path/'scenarios',
        lambda *args: pytest.fail('Pause/resume must not dispatch'))
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), 'exec'), env)
    handler = env['Handler']()
    statuses = []
    handler._headers = lambda status=200: statuses.append(status)
    def request(path, body=None):
        handler.path = path
        handler.wfile = io.BytesIO()
        if body is None:
            handler.do_GET()
        else:
            payload = json.dumps(body).encode()
            handler.headers = {'Content-Length': str(len(payload))}
            handler.rfile = io.BytesIO(payload)
            handler.do_POST()
        return json.loads(handler.wfile.getvalue())
    capabilities = request('/batches/capabilities')
    assert capabilities['ok'] and len(capabilities['models']) == 6
    assert capabilities['preflight_required'] is True
    assert not catalog.root.exists()
    created = request('/batches/create', dimensions())
    assert created['ok'] and created['dispatched'] is False
    batch_id = created['batch_id']
    assert request('/batches')['batches'][0]['batch_id'] == batch_id
    report = request('/batches/report?batch_id='+batch_id)['report']
    assert report['state_counts'] == {'pending': 1}
    paused = request('/batches/control', {'batch_id': batch_id, 'action': 'pause'})
    assert paused['paused'] and paused['dispatched'] is False
    assert request('/batches/report?batch_id='+batch_id)['report']['paused'] is True
    assert request('/batches/report?batch_id=../outside')['ok'] is False
    assert statuses[-1] == 400
    assert request('/batches/create', [])['ok'] is False
    assert statuses[-1] == 400
    assert len(catalog.list()['batches']) == 1
    matrix = dimensions()
    matrix['weather'] = [{'id': 'clear', 'configuration': {}},
                         {'id': 'rain', 'configuration': {'precipitation': 75}}]
    pair_id = request('/batches/create', matrix)['batch_id']
    url = '/batches/compare?batch_id='+pair_id+'&axis=weather&baseline=clear&candidate=rain'
    comparison = request(url)['comparison']
    assert comparison['comparable_count'] == 0
    assert len(comparison['pairs']) == 1
    assert comparison['pairs'][0]['reason'] == 'Both executions need verified completed metrics'
    assert request(url.replace('axis=weather', 'axis=seeds'))['ok'] is False
    assert statuses[-1] == 400
    assert request(url.replace('candidate=rain', 'candidate=clear'))['ok'] is False
    assert statuses[-1] == 400
    assert all(j['attempts'] == [] for j in catalog.read(pair_id)['jobs'])

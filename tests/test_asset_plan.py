import hashlib
import json

import pytest
from carla_safety_agent.asset_plan import archive_plan, compile_asset, read_plan
from carla_safety_agent.blender_pipeline import BlenderPipeline

TEXT = '生成一个蓝色长方体，长2米，宽40厘米，高0.8米，粗糙度0.6'


def test_explicit_description_and_archived_bytes(tmp_path):
    result = archive_plan(tmp_path, TEXT)
    plan = read_plan(tmp_path, result['plan_sha256'])
    assert plan['spec']['dimensions'] == [2, .4, .8]
    assert plan['spec']['shape'] == 'cube' and plan['spec']['roughness'] == .6
    assert plan['warnings'] == []
    raw = (tmp_path / (result['plan_sha256'] + '.json')).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == result['plan_sha256']
    assert archive_plan(tmp_path, TEXT) == result


@pytest.mark.parametrize('text', ['', '生成一个飞船', TEXT+'，添加摄像头',
    TEXT+'，长3米', '生成一个长方体，长2米，宽2米', TEXT.replace('40厘米', '0厘米'),
    TEXT.replace('0.6', '2'), TEXT.replace('2米', '2'), TEXT+'，创建一个球体'])
def test_unsupported_or_ambiguous_is_rejected(text):
    with pytest.raises(ValueError):
        compile_asset(text)


def test_defaults_and_plane_limit_are_visible():
    plan = compile_asset('创建平面，长2米，宽3米，高1米')
    assert len(plan['warnings']) == 3
    assert plan['spec']['shape'] == 'plane'


def test_tampering_and_unconfirmed_execution_do_not_launch(tmp_path, monkeypatch):
    pipeline = BlenderPipeline(tmp_path)
    result = pipeline.preview_plan({'description': TEXT})
    monkeypatch.setattr(pipeline, 'run', lambda *a, **kw: pytest.fail('Must not launch'))
    for data in ({'plan_sha256': result['plan_sha256'], 'confirmed': False},
                 {'plan_sha256': result['plan_sha256'], 'confirmed': True, 'shape': 'sphere'}):
        with pytest.raises(ValueError):
            pipeline.execute_plan(data)
    path = pipeline.runtime / 'plans' / (result['plan_sha256'] + '.json')
    old = path.read_bytes()
    path.write_bytes(old + b' ')
    with pytest.raises(ValueError, match='content changed'):
        pipeline.execute_plan({'plan_sha256': result['plan_sha256'], 'confirmed': True})
    assert path.read_bytes() == old + b' '


def test_confirmed_execution_uses_only_archived_spec(tmp_path, monkeypatch):
    pipeline = BlenderPipeline(tmp_path)
    result = pipeline.preview_plan({'description': TEXT})
    received = []
    monkeypatch.setattr(pipeline, 'run', lambda spec, **kw: received.append((spec, kw)) or {'ok': True})
    assert pipeline.execute_plan({'plan_sha256': result['plan_sha256'], 'confirmed': True})['ok']
    assert received == [(result['plan']['spec'], {'plan_sha256': result['plan_sha256']})]

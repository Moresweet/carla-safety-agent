import json
from types import SimpleNamespace
import numpy as np
import pytest
from carla_safety_agent.sensor_capture import depth_meters, bev_preview, calibration
from carla_safety_agent.provenance import ActorProvenance
from carla_safety_agent.replay import replay_file, replay_index
from carla_safety_agent.uv_audit import audit_uv


def test_depth_channel_order_and_units():
    values = np.array([[[0,0,0,255], [255,255,255,255], [0,0,1,255]]], dtype=np.uint8)
    meters = depth_meters(values)
    assert meters.dtype == np.float32
    assert meters[0,0] == 0
    assert meters[0,1] == pytest.approx(1000)
    assert meters[0,2] == pytest.approx(1000/16777215)


def test_lidar_bev_orientation():
    view = bev_preview(np.array([[10,10,1,.5], [np.nan,0,0,0]]), size=600, extent=60)
    assert view.shape == (600,600,3)
    assert (view[250,350] != [9,18,29]).any()


def test_calibration_focal():
    c = calibration(dict(type='sensor.camera.rgb', width=640, height=360, fov=90))
    assert c['K'][0][0] == pytest.approx(320)
    assert c['K'][1][2] == 180


def test_provenance_survives_restart_not_episode_change(tmp_path):
    actor = SimpleNamespace(id=12, type_id='vehicle.test')
    path = tmp_path/'origins.json'
    ActorProvenance(path).mark(1,[actor],'user')
    restored = ActorProvenance(path)
    assert restored.origin(1,actor) == 'user'
    restored.mark(1,[actor],'evaluation',overwrite=False)
    assert restored.origin(1,actor) == 'user'
    assert restored.origin(2,actor) == 'existing'
    assert restored.origin(1,SimpleNamespace(id=12,type_id='walker.test')) == 'existing'


def test_replay_is_confined_to_indexed_frames(tmp_path):
    run=tmp_path/'test'; folder=run/'samples'/'0000000001';folder.mkdir(parents=True)
    (run/'manifest.json').write_text('{}')
    (run/'index.json').write_text(json.dumps({'frames':[{'frame':1,'path':'samples/0000000001'}]}))
    (folder/'frame.json').write_text('{}')
    assert replay_file(tmp_path,'test',1,'frame.json') == folder/'frame.json'
    for name in ('../manifest.json','/etc/passwd'):
        with pytest.raises(ValueError): replay_file(tmp_path,'test',1,name)
    with pytest.raises(ValueError): replay_file(tmp_path,'test',2,'frame.json')
    with pytest.raises(ValueError): replay_index(tmp_path,'../test')


def test_uv_audit_reports_missing_and_invalid(tmp_path):
    (tmp_path/'vehicle-mesh-catalog.json').write_text(json.dumps({'a':{'url':'/a.json'}, 'b':{'url':'/b.json'}}))
    (tmp_path/'a.json').write_text(json.dumps({'vertices':[0]*15}))
    audit = audit_uv(tmp_path)
    assert audit['exported'] == 1
    assert audit['assets']['b']['status'] == 'missing_export'
    assert audit['other_categories'] == 'not_exported'

"""Opt-in exclusive-owner gate regression; only destroys its own probe sensor."""
import json
import uuid
from urllib.error import HTTPError
from regression_scene_versions import ROOT, request


def main():
    assert request('system/preflight')['ready']
    assert request('batches/scheduler')['scheduler']['state']!='running'
    before=request('session/status')['session']
    plan=request('scenario/compile',{'description':'Town04 前车急刹','max_duration_s':1})
    payload={'action':'rule-run','route':plan['scenario_path'],'scenario_sha256':plan['scenario_sha256']}
    import carla
    client=carla.Client('127.0.0.1',2000);client.set_timeout(10)
    world=client.get_world();episode=world.id;original=world.get_settings()
    assert not original.synchronous_mode
    def unchanged():
        current=request('session/status')['session']
        assert (current['run_id'],current['state'])==(before['run_id'],before['state'])
        assert client.get_world().id==episode
    def rejected(reason):
        assert request('system/preflight')['ready'] is False
        try: request('e2e/start',payload)
        except HTTPError as exc:
            assert exc.code==400 and reason in json.load(exc)['error']
        else: raise AssertionError('Non-exclusive start was accepted')
        unchanged()
    sensor=world.spawn_actor(world.get_blueprint_library().find('sensor.other.gnss'),carla.Transform())
    try:
        assert world.wait_for_tick(5).find(sensor.id) is not None
        rejected('Live sensors')
        assert sensor.is_alive, 'Readiness gate must not delete another owner sensor'
    finally:
        unchanged()
        assert sensor.destroy()
        assert world.wait_for_tick(5).find(sensor.id) is None
    try:
        settings=world.get_settings();settings.synchronous_mode=True;settings.fixed_delta_seconds=.05
        world.apply_settings(settings)
        rejected('synchronous owner')
        assert world.get_settings().synchronous_mode, 'Readiness gate changed another owner settings'
    finally:
        unchanged()
        world.apply_settings(original)
    assert request('system/preflight')['ready']
    result={'passed':True,'episode':episode,'probe_sensor_id':sensor.id,'probe_removed':True,
            'foreign_sensor_preserved_until_probe_cleanup':True,'foreign_sync_preserved_until_probe_cleanup':True,
            'session_unchanged':True,'scope':'Two intentional start rejections, not recovery from native crash'}
    output=ROOT/'runs/validation'/('world-readiness-'+uuid.uuid4().hex+'.json')
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,indent=2))
    print(json.dumps({'report':str(output),**result}),flush=True)


if __name__=='__main__':main()

"""Explicit native fixture: browser transform draft, bounded prop, restore camera."""
import argparse
import subprocess
import json
import urllib.error
import carla
from regression_scene_versions import ROOT, request


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--node',required=True)
    parser.add_argument('--expect-draft-reset',action='store_true')
    args=parser.parse_args()
    assert request('system/preflight')['ready']
    client=carla.Client('127.0.0.1',2000);client.set_timeout(10)
    world=client.get_world();episode=world.id;camera=world.get_spectator().get_transform()
    actor=None
    try:
        actor=request('objects/spawn',{'blueprint_id':'static.prop.advertisement',
            'transform':{'location':{'x':393.098,'y':-228.088,'z':2.5}}})['object']['id']
        if not args.expect_draft_reset:
            item=next(row for row in request('catalog/objects?category=spawned_props')['objects'] if row['id']==actor)
            expected={**item['edit_identity'],'location':item['location'],'yaw':item['rotation']['yaw']}
            def rejected(review):
                try:request('objects/update-reviewed',{'actor_id':actor,'transform':{'location':{'x':400}},'expected':review})
                except urllib.error.HTTPError as exc:
                    assert exc.code==400;assert json.load(exc)['error']
                else:raise AssertionError('Stale reviewed edit was accepted')
            for invalid in [None,{**expected,'episode':str((episode+1)%2**64)},{**expected,'type_id':'vehicle.audi.a2'}]:
                rejected(invalid)
                assert abs(world.get_actor(actor).get_location().x-item['location']['x'])<.01
            request('objects/update',{'actor_id':actor,'transform':{'location':{'x':393.598}}})
            rejected(expected)
            assert abs(world.get_actor(actor).get_location().x-393.598)<.01
            request('objects/update',{'actor_id':actor,'transform':{'location':{'x':393.098}}})
        cmd=[args.node,str(ROOT/'tools/browser_reviewed_models.mjs'),'--transform-draft',str(actor)]
        if args.expect_draft_reset:cmd.append('--expect-draft-reset')
        subprocess.run(cmd,cwd=ROOT,check=True,timeout=180)
        assert client.get_world().id==episode
        assert not world.get_settings().synchronous_mode
        assert not list(world.get_actors().filter('sensor.*'))
    finally:
        if client.get_world().id==episode:
            if actor is not None:request('objects/delete',{'actor_id':actor})
            world.get_spectator().set_transform(camera)
    print(json.dumps({'fixture_cleaned':True,'episode':str(episode),'stale_world_type_pose_rejected':not args.expect_draft_reset}))


if __name__=='__main__':main()

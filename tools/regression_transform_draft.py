"""Explicit native fixture: browser transform draft, bounded prop, restore camera."""
import argparse
import subprocess
import json
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
    print(json.dumps({'fixture_cleaned':True,'episode':str(episode)}))


if __name__=='__main__':main()

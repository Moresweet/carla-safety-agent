"""Reject malformed transforms before native lookup; never spawn or move actors."""
import json
import urllib.error
from regression_scene_versions import request


def main():
    before=request('session/status')['session']
    invalid=[None,{'scale':1},{'location':None},{'rotation':{'x':2}},
             {'location':{'x':True}},{'location':{'x':'2'}},
             {'location':{'x':float('nan')}},{'rotation':{'yaw':float('inf')}}]
    for transform in invalid:
        try:
            request('objects/update',{'actor_id':0,'transform':transform})
        except urllib.error.HTTPError as exc:
            assert exc.code==400
            error=json.load(exc)
            assert error['ok'] is False
            assert any(word in error['error'] for word in ('Transform','transform')),error
            assert 'Actor' not in error['error'], 'Native lookup occurred before validation'
        else:
            raise AssertionError('Invalid transform accepted')
    after=request('session/status')['session']
    assert (after['run_id'],after['state'])==(before['run_id'],before['state'])
    print(json.dumps({'rejected':len(invalid),'session_unchanged':True}))


if __name__=='__main__': main()

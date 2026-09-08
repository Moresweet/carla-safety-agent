"""Read-only HTTP regression against an explicitly selected recorded dataset."""
import argparse
import json
import urllib.error
import urllib.parse
import urllib.request


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('run_id')
    parser.add_argument('--base',default='http://127.0.0.1:8765')
    args=parser.parse_args()
    def get(path,**query):
        with urllib.request.urlopen(args.base+path+'?'+urllib.parse.urlencode(query),timeout=15) as response:
            return json.load(response)
    index=get('/datasets/index',run_id=args.run_id)
    frame=index['frames'][0]['frame']
    counts={}
    for camera in ('CAM_FRONT','CAM_FRONT_LEFT','CAM_FRONT_RIGHT','CAM_BACK','CAM_BACK_LEFT','CAM_BACK_RIGHT'):
        result=get('/datasets/projection',run_id=args.run_id,frame=frame,camera=camera)
        assert result['ok'] and result['frame']==frame and result['camera']==camera
        assert len(result['pixels'])==len(result['depth'])==len(result['point_indices'])<=5000
        assert result['occlusion_checked'] is False
        assert all(0<=x<result['width'] and 0<=y<result['height'] for x,y in result['pixels'])
        assert all(z>0 for z in result['depth'])
        counts[camera]=result['visible_count']
    for requested_frame,camera in ((-1,'CAM_FRONT'),(frame,'invalid')):
        try:
            get('/datasets/projection',run_id=args.run_id,frame=requested_frame,camera=camera)
        except urllib.error.HTTPError as exc:
            assert exc.code==400
            assert json.load(exc)['ok'] is False
        else:
            raise AssertionError('Invalid projection request accepted')
    print(json.dumps({'run_id':args.run_id,'frame':frame,'counts':counts,'invalid_requests_rejected':True}))


if __name__=='__main__': main()

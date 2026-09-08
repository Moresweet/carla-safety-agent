"""Read-only HTTP regression against an explicitly selected recorded dataset."""
import argparse
import json
import math
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
    events=get('/datasets/events',run_id=args.run_id)
    assert events['ok'] and events['source']=='recorded_control'
    assert events['collision_detection_available'] == events['collisions']['available']
    assert events['sample_count']==len(index['frames'])
    positions={entry['frame']:offset for offset,entry in enumerate(index['frames'])}
    collision_frames=set()
    for event in events['collisions']['events']:
        nearest=min(index['frames'], key=lambda entry:(abs(entry['frame']-event['frame']),entry['frame']))
        assert event['replay_frame']==nearest['frame'], 'Collision does not seek to nearest saved frame'
        assert event['exact_saved_frame']==(nearest['frame']==event['frame'])
        assert math.isclose(event['replay_time_offset_s'],nearest['timestamp']-event['timestamp'],abs_tol=1e-9)
        collision_frames.add(nearest['frame'])
    for collision_frame in sorted(collision_frames):
        sample=get('/datasets/frame',run_id=args.run_id,frame=collision_frame)
        assert sample['frame']==collision_frame, 'Collision seek target cannot be loaded'
    previous_end=-1
    for event in events['events']:
        start,end=positions[event['start_frame']],positions[event['end_frame']]
        assert start<=end and start>previous_end
        assert event['sample_count']==end-start+1
        assert event['start_timestamp']==index['frames'][start]['timestamp']
        assert .5<=event['peak_brake']<=1
        for boundary in (event['start_frame'],event['end_frame']):
            sample=get('/datasets/frame',run_id=args.run_id,frame=boundary)
            assert sample['frame']==boundary and sample['control']['brake']>=.5
        previous_end=end
    counts={}
    for entry in (index['frames'][0],index['frames'][-1]):
        trajectory=get('/datasets/trajectory',run_id=args.run_id,frame=entry['frame'])
        assert trajectory['ok'] and trajectory['source']=='recorded_ego_pose'
        assert not trajectory['interpolated']
        assert all(p['dt_s']<=0 for p in trajectory['history'])
        assert all(p['dt_s']>0 for p in trajectory['future'])
    assert trajectory['future']==[], 'Last recorded frame cannot have future observations'
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
    print(json.dumps({'run_id':args.run_id,'frame':frame,'counts':counts,
                     'braking_segments':len(events['events']),
                     'collision_events':len(events['collisions']['events']),
                     'collision_seek_frames_verified':len(collision_frames),'invalid_requests_rejected':True}))


if __name__=='__main__': main()

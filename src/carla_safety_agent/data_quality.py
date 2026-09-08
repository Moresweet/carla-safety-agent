"""Temporal index audit. Gaps are observations, not inferred sensor drop counts."""
import math


def temporal_quality(entries, sampling_every=None):
    if sampling_every is not None and (isinstance(sampling_every,bool) or
        not isinstance(sampling_every,int) or sampling_every<1):
        raise ValueError('Invalid sampling interval')
    errors,gaps=[],[]
    previous=None
    for offset,entry in enumerate(entries):
        frame,timestamp=entry.get('frame'),entry.get('timestamp')
        if (isinstance(frame,bool) or not isinstance(frame,int) or frame<0 or
            isinstance(timestamp,bool) or not isinstance(timestamp,(int,float)) or
            not math.isfinite(timestamp)):
            errors.append({'index':offset,'reason':'invalid_frame_or_timestamp'})
            previous=None
            continue
        if previous is not None:
            df,dt=frame-previous['frame'],timestamp-previous['timestamp']
            if df<=0 or dt<=0:
                errors.append({'index':offset,'reason':'non_monotonic','frame_delta':df,'time_delta_s':dt})
            elif sampling_every is not None and df!=sampling_every:
                gaps.append({'from_frame':previous['frame'],'to_frame':frame,
                             'frame_delta':df,'time_delta_s':dt})
        previous=entry
    return {'sample_count':len(entries),'sampling_every_frames':sampling_every,
            'temporal_order_valid':not errors,'errors':errors,'unexpected_intervals':gaps,
            'gap_check_available':sampling_every is not None,
            'note':'Unexpected intervals can reflect skipped captures or recording pauses; not sensor drop counts.'}

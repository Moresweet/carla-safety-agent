from carla_safety_agent.data_quality import temporal_quality


def test_sampling_does_not_count_normal_downsampling_as_missing():
    entries=[{'frame':f,'timestamp':f*.05} for f in (3,6,12)]
    result=temporal_quality(entries,3)
    assert result['temporal_order_valid']
    assert len(result['unexpected_intervals'])==1
    assert result['unexpected_intervals'][0]['from_frame']==6
    assert not temporal_quality(entries)['gap_check_available']


def test_bad_temporal_order_is_explicit():
    result=temporal_quality([{'frame':3,'timestamp':1},{'frame':3,'timestamp':1},
                             {'frame':4,'timestamp':float('nan')}],1)
    assert not result['temporal_order_valid'] and len(result['errors'])==2

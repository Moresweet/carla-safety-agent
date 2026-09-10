"""Optimistic actor identity/pose guard; not a world transaction or authorization."""
from .scene_store import finite_number


def validate_review(review):
    if not isinstance(review,dict) or set(review)!={'episode','actor_id','type_id','location','yaw'}:
        raise ValueError('A complete observed actor identity and pose is required')
    episode=review['episode']
    if not isinstance(episode,str) or not episode.isascii() or not episode.isdigit() or not 0<=int(episode)<2**64:
        raise ValueError('Invalid observed world identity')
    if type(review['actor_id']) is not int or not 0<review['actor_id']<2**32:
        raise ValueError('Invalid observed actor ID')
    if not isinstance(review['type_id'],str) or not 1<=len(review['type_id'])<=256:
        raise ValueError('Invalid observed actor type')
    location=review['location']
    if not isinstance(location,dict) or set(location)!={'x','y','z'} or not all(finite_number(v) for v in location.values()) or not finite_number(review['yaw']):
        raise ValueError('Invalid observed actor pose')
    return review


def verify_review(review,episode,actor,current):
    validate_review(review)
    if not all(finite_number(getattr(current.location,key)) for key in ('x','y','z')) or not finite_number(current.rotation.yaw):
        raise ValueError('Current actor pose is not finite')
    if (review['episode']!=str(episode) or review['actor_id']!=actor.id or review['type_id']!=actor.type_id):
        raise ValueError('World or actor changed since editing began; discard draft and select the current object')
    if any(abs(review['location'][key]-getattr(current.location,key))>.02 for key in ('x','y','z')) or abs((review['yaw']-current.rotation.yaw+180)%360-180)>.05:
        raise ValueError('Actor moved since editing began; discard draft and read its latest position before editing again')

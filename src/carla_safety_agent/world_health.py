"""Read-only post-exit observation; never advances the world with tick()."""
import time

from .world_readiness import map_matches, require_idle_native_world


def observe_idle(client, expected_map, seconds=5, *, clock=time.monotonic, pause=time.sleep):
    if not isinstance(seconds,(int,float)) or isinstance(seconds,bool) or not 1<=seconds<=30:
        raise ValueError('Observation window must be 1..30 seconds')
    first=client.get_world()
    episode=first.id
    frames=[]
    deadline=clock()+seconds
    while True:
        world=client.get_world()
        if world.id!=episode or not map_matches(expected_map,world.get_map().name):
            raise RuntimeError('World identity changed during post-exit observation')
        require_idle_native_world(world)
        frame=world.get_snapshot().frame
        if frames and frame<frames[-1]:raise RuntimeError('World frame counter moved backward')
        frames.append(frame)
        if clock()>=deadline:break
        pause(.25)
    if frames[-1]<=frames[0]:raise RuntimeError('Asynchronous world did not advance')
    return {'episode':episode,'map':expected_map,'observation_s':seconds,
            'frames_first_last':[frames[0],frames[-1]],'checks':len(frames),
            'synchronous':False,'sensors':0}

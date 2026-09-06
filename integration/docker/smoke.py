#!/usr/bin/env python3
"""Exercise the image's RPC, camera rendering and modified vehicle material path."""
import argparse
import json
import queue
import sys
import time
from pathlib import Path

import carla
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tools'))
from livery_bridge import runtime_name_for_actor

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--keep-vehicle', action='store_true')
    args = parser.parse_args()
    output = ROOT/'runs/docker-smoke'
    output.mkdir(parents=True, exist_ok=True)
    client = carla.Client('127.0.0.1', 2000)
    client.set_timeout(30)
    world = client.get_world()
    vehicle = camera = None
    try:
        bp = world.get_blueprint_library().find('vehicle.tesla.model3')
        bp.set_attribute('role_name', 'hero')
        for transform in world.get_map().get_spawn_points():
            vehicle = world.try_spawn_actor(bp, transform)
            if vehicle:
                break
        assert vehicle is not None, 'No free spawn point'
        vehicle.set_simulate_physics(False)
        cam_bp = world.get_blueprint_library().find('sensor.camera.rgb')
        cam_bp.set_attribute('image_size_x', '640')
        cam_bp.set_attribute('image_size_y', '360')
        cam_bp.set_attribute('sensor_tick', '0.2')
        camera = world.spawn_actor(cam_bp, carla.Transform(
            carla.Location(x=-6, y=-3, z=3), carla.Rotation(pitch=-20, yaw=25)), attach_to=vehicle)
        frames = queue.Queue(maxsize=2)
        def receive(frame):
            if frames.full():
                try:
                    frames.get_nowait()
                except queue.Empty:
                    pass
            frames.put_nowait(frame)
        camera.listen(receive)
        time.sleep(2)
        world.get_spectator().set_transform(camera.get_transform())
        target = runtime_name_for_actor(world, vehicle)
        arrays = []
        for label, color in [('green', carla.Color(0, 255, 0, 255)),
                             ('magenta', carla.Color(255, 0, 255, 255))]:
            texture = carla.TextureColor(32, 32)
            for y in range(32):
                for x in range(32):
                    texture.set(x, y, color)
            world.apply_color_texture_to_object(target, carla.MaterialParameter.Diffuse, texture)
            time.sleep(2)
            while not frames.empty():
                frames.get_nowait()
            frame = frames.get(timeout=30)
            rgb = np.frombuffer(frame.raw_data, dtype=np.uint8).reshape(360, 640, 4)[:, :, :3][:, :, ::-1].copy()
            Image.fromarray(rgb).save(output/f'{label}.png')
            arrays.append(rgb.astype(np.int16))
        changed = float(np.mean(np.max(np.abs(arrays[1]-arrays[0]), axis=2) > 40))
        report = {'map': world.get_map().name, 'actor_id': vehicle.id,
                  'object_name': target, 'changed_pixel_fraction': changed,
                  'camera_frames': True, 'texture_render_changed': changed > 0.01}
        (output/'report.json').write_text(json.dumps(report, indent=2)+'\n')
        print(json.dumps(report, indent=2))
        assert changed > 0.01, 'Texture upload did not visibly change the rendered vehicle'
    finally:
        if camera:
            camera.stop()
            camera.destroy()
        if vehicle and not args.keep_vehicle:
            vehicle.destroy()

if __name__ == '__main__':
    main()

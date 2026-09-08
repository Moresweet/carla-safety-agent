"""Read-only dependency observations, never a claim of successful world restore."""
from .material_library import MaterialLibrary


def diagnose(manifest, client, material_root):
    required = manifest['dependencies']
    # CARLA returns /Game/... paths while world snapshots omit the initial slash.
    normalize = lambda name: name.removeprefix('/Game/').lstrip('/')
    maps = {normalize(name) for name in client.get_available_maps()}
    world = client.get_world()
    current_map = normalize(world.get_map().name)
    blueprints = {blueprint.id for blueprint in world.get_blueprint_library()}
    names = set(world.get_names_of_all_objects())
    library = MaterialLibrary(material_root)
    checks = []
    for name in required['maps']:
        normalized = normalize(name)
        available = normalized in maps or normalized.rsplit('/', 1)[-1] in {m for m in maps if '/' not in m}
        checks.append({'kind': 'map', 'reference': name,
                       'state': 'available' if available else 'missing'})
    for name in required['blueprints']:
        checks.append({'kind': 'blueprint', 'reference': name,
                       'state': 'available' if name in blueprints else 'missing'})
    for map_name, target, component, slot in required['material_slots']:
        check = {'kind': 'material_slot', 'reference': [map_name, target, component, slot]}
        if normalize(map_name) != current_map:
            check.update(state='not_checked', reason='Map is not loaded; diagnostic never switches maps')
        else:
            entries = library.catalog(map_name)['actors'].get(target, [])
            matches = [s for entry in entries if entry['component'] == component
                       for s in entry['slots'] if s['slot'] == slot and s.get('status') == 'uv0_ready']
            check.update(state='available' if target in names and len(matches) == 1 else 'missing',
                         reason='Requires live target and one verified UV0 catalog slot')
        checks.append(check)
    return {'checks': checks, 'all_declared_dependencies_available': all(c['state'] == 'available' for c in checks),
            'current_map': current_map, 'live_world_modified': False, 'restore_verified': False,
            'limitations': ['Checks declarations, not engine patch compatibility or actual spawn/material application',
                            'External asset bytes and model weights are not included or verified']}

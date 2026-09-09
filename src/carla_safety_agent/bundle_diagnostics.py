"""Read-only dependency observations, never a claim of successful world restore."""
from .material_library import MaterialLibrary
from .material_mesh import validate_preview


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
        check = {'kind': 'blueprint', 'reference': name,
                 'state': 'available' if name in blueprints else 'missing'}
        if name.startswith('generated.prop.'):
            check.update(state='not_checked',
                         source_package_included=name in required.get('generated_asset_sources', {}),
                         reason='Generated ID is a studio registry alias; native Blueprint enumeration cannot verify its target mesh')
        checks.append(check)
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
            if check['state'] == 'available':
                try:
                    path = library.mesh(map_name.split('/')[-1], matches[0].get('mesh_file'))
                    if path.stat().st_size > 32*1024*1024: raise ValueError('Preview too large')
                    validate_preview(path.read_bytes())
                    check['reason'] = 'Live target, unique UV0 slot and valid XYZ/UV preview file'
                except (OSError, ValueError, TypeError, KeyError) as exc:
                    check.update(state='missing', reason=f'Preview unavailable: {exc}')
        checks.append(check)
    return {'checks': checks, 'all_declared_dependencies_available': all(c['state'] == 'available' for c in checks),
            'current_map': current_map, 'live_world_modified': False, 'restore_verified': False,
            'limitations': ['Checks declarations, not engine patch compatibility or actual spawn/material application',
                            'Bundled source packages do not prove target Unreal import or registry availability',
                            'Model weights are not included or verified']}

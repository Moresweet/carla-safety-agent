"""Exact-slot, overlay-only texture variants; no implicit world/map changes."""
from .material_library import material_edits


def texture_records(configuration):
    if configuration == {}:
        return []  # Baseline means the current editor state, not factory defaults.
    if not isinstance(configuration, dict) or set(configuration) != {'environment_materials'}:
        raise ValueError('Texture variant requires only environment_materials')
    records = configuration['environment_materials']
    material_edits(records)
    return records


def overlay_materials(before, configuration):
    merged = material_edits(before)
    merged.update(material_edits(texture_records(configuration)))
    return [{'target': k[0], 'component': k[1], 'slot': k[2], 'texture': digest}
            for k, digest in sorted(merged.items())]


def require_texture_world(world, scenario):
    if scenario.get('generated_map') or scenario['map_name'].split('/')[-1].lower() != world.get_map().name.split('/')[-1].lower():
        raise ValueError('Texture variants require the current map; map switching is forbidden')
    if world.get_settings().synchronous_mode:
        raise ValueError('Texture variants require an idle asynchronous world')

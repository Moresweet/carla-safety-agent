"""Select one object and its versioned materials without global scene state."""
from .scene_store import identifier, validate_scene


def object_restore_document(document, stable_id):
    identifier(stable_id)
    source = validate_scene(document)
    selected = [obj for obj in source['objects'] if obj['stable_id'] == stable_id]
    if len(selected) != 1:
        raise ValueError('Selected object is missing from the snapshot')
    return validate_scene({
        'schema_version': 'carla-scene/1', 'map': source['map'],
        'objects': selected,
        'actor_materials': [item for item in source.get('actor_materials', [])
                           if item['stable_id'] == stable_id],
    })

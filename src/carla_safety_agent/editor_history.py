"""Read-only index of durable editor journals, never an undo authorization."""
from .scene_store import read_json


def editor_history(transforms, deletions, limit=50, copies=None, materials=None, actor_materials=None):
    if type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError('Editor history limit must be 1..200')
    rows, warnings = [], []
    if transforms.root.is_symlink() or deletions.root.is_symlink():
        raise ValueError('Linked editor history refused')
    # Hold the writer lock so cursor, entries and pending intent agree.
    with transforms.lock:
        if transforms.root.exists():
            for count, folder in enumerate(transforms.root.iterdir()):
                if count >= 10000:
                    raise ValueError('Editor history scan limit exceeded')
                try:
                    if folder.is_symlink() or not folder.is_dir():
                        raise ValueError('Unexpected transform history entry')
                    path = folder / 'current.json'
                    if path.is_symlink():
                        raise ValueError('Linked transform journal refused')
                    identity = read_json(path, max_bytes=4*1024**2).get('identity')
                    if transforms.folder(identity) != folder:
                        raise ValueError('Transform journal directory identity mismatch')
                    journal = transforms.read(identity)
                    for index, entry in enumerate(journal['entries']):
                        rows.append({'kind':'transform', 'operation_id':entry['id'],
                            'created_at':entry['created_at'], 'identity':identity,
                            'state':'applied' if index < journal['cursor'] else 'undone',
                            'revision':journal['revision'], 'before':entry['before'],
                            'after':entry['after']})
                    pending = journal['pending']
                    if pending:
                        rows.append({'kind':'transform-intent', 'operation_id':pending['id'],
                            'created_at':None, 'identity':identity, 'state':pending['state'],
                            'revision':journal['revision'], 'intent':pending})
                except (ValueError, OSError, AttributeError) as error:
                    warnings.append({'source':folder.name, 'error':str(error)})
    # Read every validated deletion, not only its first page before global sorting.
    if deletions.root.exists():
        for count, path in enumerate(deletions.root.glob('*.json')):
            if count >= 10000:
                raise ValueError('Editor history scan limit exceeded')
            try:
                row = deletions.read(path.stem)
                rows.append({'kind':'delete', **row})
            except (ValueError, OSError) as error:
                warnings.append({'source':path.name, 'error':str(error)})
    if copies is not None:
        if copies.root.is_symlink():
            raise ValueError('Linked copy journal refused')
        for count, path in enumerate(copies.root.glob('*.json')):
            if count >= 10000:
                raise ValueError('Editor history scan limit exceeded')
            try:
                rows.append(copies.read(path.stem))
            except (ValueError, OSError) as error:
                warnings.append({'source':path.name, 'error':str(error)})
    if materials is not None:
        if materials.root.is_symlink():
            raise ValueError('Linked material journal refused')
        for count, path in enumerate(materials.root.glob('*.json')):
            if count >= 10000:raise ValueError('Editor history scan limit exceeded')
            try:rows.append(materials.read(path.stem))
            except (ValueError,OSError) as error:
                warnings.append({'source':path.name,'error':str(error)})
    if actor_materials is not None:
        if actor_materials.root.is_symlink():raise ValueError('Linked actor material journal refused')
        for count,path in enumerate(actor_materials.root.glob('*.json')):
            if count>=10000:raise ValueError('Editor history scan limit exceeded')
            try:rows.append(actor_materials.read(path.stem))
            except (ValueError,OSError) as error:
                warnings.append({'source':path.name,'error':str(error)})
    # Pending transform intents have no historical timestamp in the old schema.
    # Surface them first without inventing a time or silently omitting them.
    rows.sort(key=lambda row: (row['created_at'] is None,
                              row['created_at'] or 0, row['operation_id']), reverse=True)
    return {'entries':rows[:limit], 'total':len(rows), 'truncated':len(rows)>limit,
            'capabilities':{'actor_material_transition':actor_materials is not None},
            'complete':not warnings, 'warnings':warnings,
            'coverage':{'transform':'current chains and pending intents',
                        'delete':'durable deletion observations',
                        'copy':'local editor copies only' if copies is not None else 'not included',
                        'texture':'exact environment slots only' if materials is not None else 'not included',
                        'actor_texture':'managed supported actor slots; read-only' if actor_materials is not None else 'not included'},
            'scope':'Read-only journal index; archived transform branches excluded; '
                    'not current world state, global chronology, or undo/redo approval'}

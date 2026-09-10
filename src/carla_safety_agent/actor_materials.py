"""Exact, versionable actor slots; unknown layouts never inherit another model's UV."""
import re

SUPPORTED={'vehicle.audi.a2':('VehicleMesh',4,2048),
           'walker.pedestrian.0001':('CharacterMesh0',14,1024)}


def actor_material_edits(records,objects):
    if not isinstance(records,list) or len(records)>2000:
        raise ValueError('At most 2000 actor material overrides are supported')
    identities={obj['stable_id']:obj['blueprint_id'] for obj in objects}
    result={}
    for record in records:
        if not isinstance(record,dict) or set(record)!={'stable_id','blueprint_id','component','slot','texture'}:
            raise ValueError('Invalid actor material reference')
        stable,model,component,slot,texture=(record[key] for key in ('stable_id','blueprint_id','component','slot','texture'))
        if not isinstance(stable,str) or identities.get(stable)!=model or not isinstance(model,str) or model not in SUPPORTED:
            raise ValueError('Actor material must reference a supported object in this scene')
        expected=SUPPORTED[model]
        if type(slot) is not int or (component,slot)!=expected[:2]:
            raise ValueError('Actor material component/slot differs from the verified layout')
        if not isinstance(texture,str) or not re.fullmatch('[a-f0-9]{64}',texture):
            raise ValueError('Invalid actor texture digest')
        key=(stable,component,slot)
        if key in result:raise ValueError('Duplicate actor material reference')
        result[key]=texture
    return result


def actor_texture_digests(document):
    if 'actor_materials' not in document:return set()
    return set(actor_material_edits(document.get('actor_materials',[]),document['objects']).values())


def transaction_records(records):
    return [{'target':record['stable_id'],'component':record['component'],'slot':record['slot'],'texture':record['texture']}
            for record in records]

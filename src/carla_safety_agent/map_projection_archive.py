"""Recording-owned OpenDRIVE source for offline coordinate conversion."""
import hashlib
import xml.etree.ElementTree as ET
from pathlib import Path

MAX_BYTES=32*1024**2


def projection_text(payload):
    if not payload or len(payload)>MAX_BYTES:raise ValueError('OpenDRIVE size out of bounds')
    if b'<!DOCTYPE' in payload.upper() or b'<!ENTITY' in payload.upper():
        raise ValueError('OpenDRIVE entity declarations refused')
    doc=ET.fromstring(payload)
    if doc.tag!='OpenDRIVE':raise ValueError('Not an OpenDRIVE document')
    text=doc.findtext('./header/geoReference')
    if not text or not text.strip():raise ValueError('Map projection is missing')
    return text.strip()


def archive_map_projection(root, road_map):
    if road_map is None or not callable(getattr(road_map,'to_opendrive',None)):
        return {'state':'unavailable','reason':'Map OpenDRIVE export unavailable'}
    payload=road_map.to_opendrive().encode('utf-8')
    try:projection=projection_text(payload)
    except (ValueError,ET.ParseError) as error:
        return {'state':'unavailable','reason':str(error)}
    digest=hashlib.sha256(payload).hexdigest()
    name='map-'+digest+'.xodr'
    with (Path(root)/name).open('xb') as stream:stream.write(payload)
    return {'state':'available','schema_version':'capture-map-projection/1',
            'map_name':road_map.name,'path':name,'sha256':digest,
            'geo_reference':projection,'source':'recording_world_map.to_opendrive',
            'coordinates':'CARLA world x forward/y right/z up; metres'}


def read_map_projection(root, reference):
    if not isinstance(reference,dict) or reference.get('state')!='available':
        raise ValueError('No archived map projection; current map is not a substitute')
    digest=reference.get('sha256');name=reference.get('path')
    if (reference.get('schema_version')!='capture-map-projection/1' or
            not isinstance(digest,str) or len(digest)!=64 or
            any(c not in '0123456789abcdef' for c in digest) or name!='map-'+digest+'.xodr'):
        raise ValueError('Invalid map projection reference')
    path=Path(root)/name
    if path.is_symlink() or not path.is_file() or path.stat().st_size>MAX_BYTES:
        raise ValueError('Unsafe map projection file')
    payload=path.read_bytes()
    if hashlib.sha256(payload).hexdigest()!=digest:raise ValueError('Map projection checksum mismatch')
    if projection_text(payload)!=reference.get('geo_reference'):raise ValueError('Map projection metadata mismatch')
    return payload.decode('utf-8')

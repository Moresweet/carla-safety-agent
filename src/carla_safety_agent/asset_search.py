"""Deterministic name/category lookup over available IDs, not visual retrieval."""
import re

ALIASES = {'车辆': ('vehicle.',), '汽车': ('vehicle.',), '行人': ('walker.pedestrian.',),
           '道具': ('static.prop.', 'generated.prop.'), '生成资产': ('generated.prop.',),
           '护栏': ('barrier', 'guardrail'), '路锥': ('trafficcone', 'cone'),
           '长椅': ('bench',), '垃圾桶': ('garbage', 'trash', 'bin'),
           '特斯拉': ('tesla',), '奥迪': ('audi',), '自行车': ('bicycle', 'crossbike', 'diamondback', 'gazelle')}


def search_assets(ids, query='', *, kind='all', offset=0, limit=48):
    if not isinstance(query, str) or len(query) > 256:
        raise ValueError('Asset query must be at most 256 characters')
    if kind not in ('all', 'vehicle', 'walker', 'prop', 'generated'):
        raise ValueError('Unknown asset category')
    if type(offset) is not int or not 0 <= offset <= 100000 or type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError('Invalid asset pagination')
    terms = [ALIASES.get(term, (term,)) for term in re.split(r'\s+', query.casefold().strip()) if term]
    def category(identifier):
        return ('vehicle' if identifier.startswith('vehicle.') else
                'walker' if identifier.startswith('walker.') else 'prop')
    matches = sorted({identifier for identifier in ids if isinstance(identifier, str)
                      and identifier.startswith(('vehicle.', 'walker.pedestrian.', 'static.prop.', 'generated.prop.'))
                      and (kind == 'all' or kind == category(identifier)
                           or kind == 'generated' and identifier.startswith('generated.prop.'))
                      and all(any(word in identifier.casefold() for word in term) for term in terms)})
    page = matches[offset:offset + limit]
    return {'ok': True, 'total': len(matches), 'offset': offset, 'limit': limit,
            'blueprints': page, 'has_more': offset + len(page) < len(matches),
            'search_scope': 'Blueprint names and explicit category aliases only; appearance and geometry are not verified'}

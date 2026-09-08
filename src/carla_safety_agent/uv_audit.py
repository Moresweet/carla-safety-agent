"""Audit exported preview geometry; absence is not proof of missing Unreal UVs."""
import json
import math
from pathlib import Path


def audit_uv(public):
    public = Path(public)
    catalog = json.loads((public/'vehicle-mesh-catalog.json').read_text())
    assets = {}
    for name, entry in catalog.items():
        path = public/entry['url'].lstrip('/')
        result = {**entry, 'status': 'missing_export', 'uv_channel': 0}
        try:
            mesh = json.loads(path.read_text())
            raw = mesh.get('vertices', [])
            valid = bool(raw) and len(raw) % 15 == 0 and all(isinstance(v, (int, float)) and math.isfinite(v) for v in raw)
            result.update(status='exported_uv0' if valid else 'invalid_mesh',
                          triangles=len(raw)//15, source=mesh.get('source'))
        except (OSError, ValueError):
            pass
        assets[name] = result
    return {'assets': assets, 'exported': sum(v['status'] == 'exported_uv0' for v in assets.values()),
            'registered': len(assets), 'other_categories': 'not_exported',
            'note': '仅核验网页导出的 UV0/指定材质槽；不是 Unreal 所有资产 UV 的完整性证明。'}

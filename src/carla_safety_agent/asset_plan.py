"""Explicit Chinese primitive plans, never generated executable Blender code."""
import hashlib
import json
from pathlib import Path
import re

SHAPES = {'长方体': 'cube', '立方体': 'cube', '圆柱体': 'cylinder', '圆锥体': 'cone', '球体': 'sphere', '平面': 'plane'}
COLORS = {'蓝色': [0.15, 0.55, 0.85, 1], '红色': [0.85, 0.1, 0.1, 1],
          '黄色': [0.95, 0.8, 0.05, 1], '绿色': [0.1, 0.7, 0.2, 1],
          '白色': [1, 1, 1, 1], '黑色': [0.02, 0.02, 0.02, 1], '灰色': [0.5, 0.5, 0.5, 1]}
NUMBER = r'(?:\d+(?:\.\d+)?)'


def compile_asset(description):
    if not isinstance(description, str) or not 1 <= len(description.strip()) <= 1000:
        raise ValueError('模型描述必须为1..1000字')
    clauses = [v.strip() for v in re.split('[，,；;。\n]+', description) if v.strip()]
    if not 1 <= len(clauses) <= 10:
        raise ValueError('模型描述最多10个明确子句')
    shape, color, roughness, dimensions, used = None, None, 0.45, {}, set()
    for clause in clauses:
        match = re.fullmatch(r'(?:请)?(?:生成|创建)(?:一个|个)?(' + '|'.join(COLORS) + r')?(' + '|'.join(SHAPES) + ')', clause)
        if match:
            if 'shape' in used:
                raise ValueError('重复的形状描述')
            used.add('shape')
            color = COLORS[match[1]][:] if match[1] else None
            shape = SHAPES[match[2]]
            continue
        match = re.fullmatch(r'(长|宽|高)(?:为)?\s*(' + NUMBER + r')\s*(米|厘米|m|cm)', clause)
        if match:
            field = match[1]
            if field in used:
                raise ValueError('重复的尺寸描述')
            used.add(field)
            value = float(match[2]) / (100 if match[3] in ('厘米', 'cm') else 1)
            if not 0.01 <= value <= 1000:
                raise ValueError('每个尺寸必须在0.01..1000米之间')
            dimensions[field] = value
            continue
        match = re.fullmatch(r'粗糙度(?:为)?\s*(' + NUMBER + ')', clause)
        if match:
            if 'roughness' in used:
                raise ValueError('重复的粗糙度描述')
            used.add('roughness')
            roughness = float(match[1])
            if not 0 <= roughness <= 1:
                raise ValueError('粗糙度必须在0..1之间')
            continue
        raise ValueError('不支持的模型子句：' + clause)
    if not shape or set(dimensions) != {'长', '宽', '高'}:
        raise ValueError('请明确生成形状，以及带单位的长、宽、高；不猜测缺失尺寸')
    warnings = []
    if color is None:
        color = COLORS['蓝色'][:]
        warnings.append('未指定颜色：使用蓝色')
    if 'roughness' not in used:
        warnings.append('未指定粗糙度：使用0.45')
    if shape == 'plane':
        warnings.append('平面无实体厚度；高仅保留为输入，不会生成实体厚度')
    if shape in ('sphere', 'cylinder', 'cone'):
        warnings.append('长宽高为包围盒尺寸；不等长轴可能生成椭球/椭圆截面')
    spec = {'name': 'NLAsset_' + hashlib.sha256(description.encode()).hexdigest()[:12],
            'shape': shape, 'dimensions': [dimensions[k] for k in ('长', '宽', '高')],
            'color': color, 'roughness': roughness}
    return {'schema_version': 'carla-asset-plan/1', 'description': description,
            'spec': spec, 'warnings': warnings,
            'scope': '本地参数化基本体，不是任意文本到3D模型；不执行生成的代码'}


def archive_plan(root, description):
    from .owned_resources import durable_write
    root = Path(root)
    if root.is_symlink():
        raise ValueError('Asset plan root must not be redirected')
    root.mkdir(parents=True, exist_ok=True)
    plan = compile_asset(description)
    raw = json.dumps(plan, allow_nan=False).encode()
    digest = hashlib.sha256(raw).hexdigest()
    path = root / (digest + '.json')
    # Match durable_write's exact JSON encoding; execution verifies file bytes.
    if path.is_symlink():
        raise ValueError('Asset plan path must not be a link')
    if path.exists():
        if read_plan(root, digest) != plan:
            raise ValueError('Existing asset plan mismatch')
    else:
        durable_write(path, plan, exclusive=True)
    return {'ok': True, 'plan_sha256': digest, 'plan': plan}


def read_plan(root, digest):
    if not isinstance(digest, str) or not re.fullmatch('[a-f0-9]{64}', digest):
        raise ValueError('Invalid asset plan SHA-256')
    root = Path(root)
    path = root / (digest + '.json')
    if root.is_symlink() or path.is_symlink() or path.stat().st_size > 65536:
        raise ValueError('Invalid asset plan file')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError('Asset plan content changed')
    plan = json.loads(raw)
    if not isinstance(plan, dict) or compile_asset(plan.get('description')) != plan:
        raise ValueError('Asset plan no longer matches the supported compiler')
    return plan

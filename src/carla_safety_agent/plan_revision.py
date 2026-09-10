"""Bounded natural-language edits of an immutable compiled plan, never world RPC."""
import copy
import hashlib
import json
import re
from .io import scenario_from_dict
from .build_plan import build_plan

NUMBER=r'(\d+(?:\.\d+)?)'


def revise_plan(document,parent_sha256,instruction):
    if not isinstance(parent_sha256,str) or not re.fullmatch('[0-9a-f]{64}',parent_sha256):raise ValueError('Verified parent plan SHA-256 required')
    if not isinstance(instruction,str) or not instruction.strip() or len(instruction)>1000:raise ValueError('Revision must contain 1–1000 characters')
    if not isinstance(document,dict):raise ValueError('Parent plan must be an object')
    child=copy.deepcopy(document);changes=[];touched=set()
    build_plan(scenario_from_dict(copy.deepcopy(child)))
    provenance=child.get('provenance',{})
    if not isinstance(provenance,dict):raise ValueError('Invalid parent provenance')
    previous=provenance.get('plan_revision',{})
    if not isinstance(previous,dict):raise ValueError('Invalid parent revision lineage')
    depth=previous.get('depth',0)
    if type(depth) is not int or not 0<=depth<32:raise ValueError('Plan revision lineage limit reached')
    clauses=[part.strip() for part in re.split(r'[，,；;。\n]+',instruction.strip()) if part.strip()]
    if not 1<=len(clauses)<=8:raise ValueError('Use at most 8 explicit edit clauses')
    def put(path,value):
        key='/'.join(map(str,path))
        if key in touched:raise ValueError('Repeated or conflicting edit for '+key)
        touched.add(key);target=child
        for part in path[:-1]:target=target[part]
        before=target[path[-1]]
        if before!=value:changes.append({'path':key,'before':copy.deepcopy(before),'after':copy.deepcopy(value)})
        target[path[-1]]=value
    def principal():
        if len(child['adversaries'])!=1:raise ValueError('This edit requires exactly one principal adversary')
        return child['adversaries'][0]
    for raw in clauses:
        clause=re.sub(r'^(?:请)?(?:把|将)?\s*','',raw.strip().lower())
        if clause in ('其余不变','其他不变','其余保持不变','其他保持不变'):continue
        match=re.fullmatch(r'(自车速度|对手速度|前车速度)\s*(?:改为|设为|设置为)\s*'+NUMBER+r'\s*(m/s|米/秒|km/h|公里/小时)',clause)
        if match:
            role,value,unit=match.groups();speed=float(value)/(3.6 if unit in ('km/h','公里/小时') else 1)
            if not 0<=speed<=60:raise ValueError('Speed must be between 0 and 60 m/s')
            if role!='自车速度':
                other=principal()
                if role=='前车速度' and not other['blueprint'].startswith('vehicle.'):raise ValueError('Principal adversary is not a vehicle; use its explicit role')
            put(['ego','speed_mps'] if role=='自车速度' else ['adversaries',0,'speed_mps'],speed);continue
        match=re.fullmatch(r'(触发距离|运行时长|雨量|雾浓度|随机种子)\s*(?:改为|设为|设置为)\s*'+NUMBER+r'\s*(米|m|秒|s|%)?',clause)
        if match:
            field,value,unit=match.groups();number=float(value)
            if field=='触发距离':
                principal()
                if unit not in ('米','m') or not 0<number<=1000:raise ValueError('Trigger distance requires metres, greater than 0 and at most 1000')
                put(['adversaries',0,'trigger_distance_m'],number)
            elif field=='运行时长':
                if unit not in ('秒','s') or not .05<=number<=120:raise ValueError('Duration requires seconds, between 0.05 and 120')
                put(['oracle','max_duration_s'],number)
            elif field=='随机种子':
                if unit is not None or not value.isdigit() or not 0<=int(value)<=2**32-1:raise ValueError('Seed must be an unsigned 32-bit integer')
                put(['seed'],int(value))
            else:
                if unit not in (None,'%') or not 0<=number<=100:raise ValueError('Rain/fog must be between 0 and 100')
                put(['environment','precipitation' if field=='雨量' else 'fog_density'],number)
            continue
        match=re.fullmatch(r'天气\s*(?:改为|设为|设置为)\s*(晴天|大雨|小雨)',clause)
        if match:
            rain={'晴天':0.,'大雨':70.,'小雨':30.}[match[1]]
            put(['environment','precipitation'],rain);put(['environment','cloudiness'],rain)
            if match[1]=='晴天':put(['environment','fog_density'],0.)
            continue
        match=re.fullmatch(r'光照\s*(?:改为|设为|设置为)\s*(白天|夜间)',clause)
        if match:put(['environment','sun_altitude_angle'],45. if match[1]=='白天' else -10.);continue
        match=re.fullmatch(r'地图\s*(?:改为|设为|设置为)\s*(town\d{2}(?:_opt)?)',clause)
        if match:
            if child.get('generated_map') is not None:raise ValueError('Do not replace a generated road through a stock-map field edit')
            name=match[1];put(['map_name'],'Town'+name[4:6]+('_Opt' if name.endswith('_opt') else ''));continue
        match=re.fullmatch(r'金属管数量\s*(?:改为|设为|设置为)\s*(\d+)\s*(?:根)?',clause)
        if match:
            count=int(match[1]);assets=child.get('generated_assets',[])
            indexes=[i for i,asset in enumerate(assets) if asset.get('shape')=='metal_pipes']
            if len(indexes)!=1 or not 1<=count<=64:raise ValueError('Requires exactly one metal-pipe asset group and count 1–64')
            put(['generated_assets',indexes[0],'count'],count);continue
        raise ValueError('Unsupported edit clause (nothing was changed): '+raw)
    if not changes:raise ValueError('Requested fields already have these values; no new revision created')
    identity=hashlib.sha256((parent_sha256+json.dumps(changes,sort_keys=True,ensure_ascii=False)).encode()).hexdigest()[:16]
    child['scenario_id']='revision-'+identity
    child['provenance']={**provenance,'plan_revision':{'schema_version':'carla-plan-revision/1','parent_sha256':parent_sha256,
        'instruction':instruction,'changes':changes,'depth':depth+1}}
    build_plan(scenario_from_dict(copy.deepcopy(child)))
    json.dumps(child,allow_nan=False)
    return child,changes

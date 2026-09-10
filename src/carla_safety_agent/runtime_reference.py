"""Portable model file identities. Never loads checkpoints or executes configs."""
import hashlib
from pathlib import Path, PurePosixPath
import re

SCHEMA = 'carla-runtime-reference/1'
MODELS = {'uniad-tiny','uniad-base','vad','tcp','admlp'}
LIMIT = 64 * 1024**3


def validate_reference(document):
    if (not isinstance(document,dict) or set(document)!={'schema_version','files'} or
            document['schema_version']!=SCHEMA or not isinstance(document['files'],list) or
            not 1<=len(document['files'])<=128):
        raise ValueError('Invalid runtime reference document')
    roles={};total=0
    for entry in document['files']:
        if not isinstance(entry,dict) or set(entry)!={'model','role','root','path','size','sha256'}:
            raise ValueError('Invalid model file reference')
        model,role,root,path=entry['model'],entry['role'],entry['root'],entry['path']
        if not isinstance(model,str) or model not in MODELS or role not in ('adapter','checkpoint','config'):
            raise ValueError('Unsupported model or file role')
        if not isinstance(root,str) or not re.fullmatch('[A-Za-z][A-Za-z0-9_-]{0,39}',root):
            raise ValueError('Invalid relocation root alias')
        if (not isinstance(path,str) or not path or len(path)>1024 or path in ('.','..') or
                any(ord(character)<32 for character in path) or '\\' in path or ':' in path or
                PurePosixPath(path).is_absolute() or str(PurePosixPath(path))!=path or
                any(part in ('.','..') for part in PurePosixPath(path).parts)):
            raise ValueError('Model file path must be a confined relative path')
        if isinstance(entry['size'],bool) or not isinstance(entry['size'],int) or not 0<entry['size']<=LIMIT:
            raise ValueError('Invalid model file size')
        if not isinstance(entry['sha256'],str) or not re.fullmatch('[a-f0-9]{64}',entry['sha256']):
            raise ValueError('Invalid model file checksum')
        selected=roles.setdefault(model,set())
        if role in selected:raise ValueError('Duplicate model file role')
        selected.add(role);total+=entry['size']
    if total>LIMIT or any(not {'adapter','checkpoint'}<=value for value in roles.values()):
        raise ValueError('Incomplete or oversized model references')
    return document


def confined_file(root, relative):
    base=Path(root).resolve()
    path=(base/relative).resolve()
    if base not in path.parents or not path.is_file():
        raise ValueError('Referenced file missing or outside relocation root')
    return path


def fingerprint(path):
    path=Path(path)
    before=path.stat()
    if not 0<before.st_size<=LIMIT:raise ValueError('Invalid model file size')
    digest=hashlib.sha256()
    consumed=0
    with path.open('rb') as stream:
        while block:=stream.read(8*1024*1024):
            consumed+=len(block)
            if consumed>LIMIT:raise ValueError('Model file exceeded size limit while hashing')
            digest.update(block)
    after=path.stat()
    identity=lambda value:(value.st_dev,value.st_ino,value.st_size,value.st_mtime_ns,value.st_ctime_ns)
    if identity(before)!=identity(after):raise ValueError('Model file changed while hashing')
    return {'size':after.st_size,'sha256':digest.hexdigest()}


def export_reference(catalog, model_ids, roots):
    if not model_ids or len(set(model_ids))!=len(model_ids) or not set(model_ids)<=MODELS:
        raise ValueError('Select unique supported model IDs')
    files=[]
    for model in model_ids:
        entry=next((item for item in catalog if item['id']==model),None)
        if entry is None or entry.get('status')!='available':raise ValueError('Selected model is unavailable')
        for role in ('adapter','checkpoint','config'):
            if not entry.get(role):continue
            original=Path(entry[role]).resolve()
            matches=[(alias,Path(root).resolve()) for alias,root in roots.items()
                     if Path(root).resolve() in original.parents]
            if len(matches)!=1:raise ValueError('Each file requires exactly one explicit relocation root')
            alias,base=matches[0]
            files.append({'model':model,'role':role,'root':alias,'path':original.relative_to(base).as_posix(),
                          **fingerprint(original)})
    return validate_reference({'schema_version':SCHEMA,'files':files})


def verify_reference(document, roots):
    validate_reference(document)
    results=[]
    for entry in document['files']:
        row={'model':entry['model'],'role':entry['role'],'root':entry['root'],'path':entry['path']}
        if entry['root'] not in roots:
            row.update(state='missing_root')
        else:
            try:
                actual=fingerprint(confined_file(roots[entry['root']],entry['path']))
                row.update(state='matched' if actual=={key:entry[key] for key in ('size','sha256')} else 'mismatch')
            except (ValueError,OSError) as error:
                row.update(state='unavailable',error=str(error))
        results.append(row)
    return {'ok':all(row['state']=='matched' for row in results),'files':results,
            'scope':'Referenced file bytes only; dependency environment and model execution are not verified.',
            'weights_loaded':False,'code_executed':False}

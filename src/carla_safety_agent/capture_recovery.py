"""Recover an interrupted capture into a new, audited copy; never repair in place."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import uuid

from .capture_quality import audit_capture
from .data_quality import validate_capture_index


def require_inactive_execution(data_root,execution_id):
    from .session import SessionJournal,ACTIVE,observed_process_identity
    journal=SessionJournal(data_root)
    if journal.snapshot().get('state') in ACTIVE:raise ValueError('Studio execution is active; recovery requires idle state')
    record=journal.read_execution(execution_id)
    identity=record.get('process')
    if not isinstance(identity,dict) or set(identity)!={'pid','start_ticks'}:
        raise ValueError('No verified historical worker identity')
    if not isinstance(identity['start_ticks'],str) or not identity['start_ticks'].isdigit():
        raise ValueError('Malformed historical worker identity')
    observed=observed_process_identity(identity['pid'])
    if observed==identity:raise ValueError('Capture worker is still alive')


def inventory(root):
    root=Path(root)
    if root.is_symlink() or not root.is_dir():raise ValueError('Invalid recovery source')
    result={};total=0
    for path in root.rglob('*'):
        if path.is_symlink():raise ValueError('Recovery source contains a symbolic link')
        if path.is_dir():continue
        if not path.is_file():raise ValueError('Recovery source contains a special file')
        total+=path.stat().st_size
        if total>20*1024**3 or len(result)>=300000:raise ValueError('Recovery source exceeds bounded size')
        digest=hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
        result[str(path.relative_to(root))]={'sha256':digest.hexdigest(),'bytes':path.stat().st_size}
    return result,total


def recover_capture(source,destination_root,validator,python,require_inactive):
    """Caller proves the recorded execution is inactive before and after auditing.

    A missing final frame.json denotes an uncommitted tail, not a valid sample.
    Malformed metadata, interior holes or corrupt raw data fail the whole copy.
    Failed attempts remain in their unique directory for inspection.
    """
    source=Path(source)
    if source.is_symlink():raise ValueError('Recovery source cannot be a link')
    source=source.resolve();destination_root=Path(destination_root).resolve()
    require_inactive()
    if (source/'manifest.json').is_symlink() or (source/'manifest.json').stat().st_size>8*1024*1024:
        raise ValueError('Invalid capture manifest path or size')
    evidence,total=inventory(source)
    manifest=json.loads((source/'manifest.json').read_text())
    if manifest.get('schema_version')!='carla-safety-dataset/0.2':raise ValueError('Only unified captures can be recovered')
    if manifest.get('status') not in ('recording','saved_cleanup_error'):
        raise ValueError('Only interrupted or cleanup-failed captures can be recovered')
    archive=manifest.get('input_archive')
    if archive not in ('sensor_input.npz','model_input.npz'):raise ValueError('Unknown capture archive')
    samples=source/'samples'
    folders=sorted(samples.iterdir())
    if len(folders)>10000:raise ValueError('Recovery supports at most 10000 sample directories')
    entries=[];omitted=[]
    for folder in folders:
        if not folder.is_dir() or not re.fullmatch(r'\d{10,}',folder.name):raise ValueError('Invalid sample directory')
        if not (folder/'frame.json').is_file():
            omitted.append(folder.name);continue
        if omitted:raise ValueError('Uncommitted sample inside capture; refusing to hide an interior hole')
        if (folder/'frame.json').stat().st_size>8*1024*1024:raise ValueError('Oversized sample metadata')
        metadata=json.loads((folder/'frame.json').read_text())
        if type(metadata.get('frame')) is not int or metadata['frame']!=int(folder.name):raise ValueError('Sample identity mismatch')
        entries.append({'frame':metadata['frame'],'timestamp':metadata['timestamp'],'path':'samples/'+folder.name})
    if not entries:raise ValueError('No committed samples to recover')
    validate_capture_index(entries,{**manifest,'frame_count':len(entries)})
    if not destination_root.is_dir():raise ValueError('Destination root must already exist')
    if shutil.disk_usage(destination_root).free<total+1024**3:raise ValueError('Insufficient space for a recovery copy')
    run_id='recovered-'+uuid.uuid4().hex
    output=destination_root/run_id
    if source==output or source in output.parents:raise ValueError('Recovery copy cannot be inside source')
    output.mkdir()
    report={'schema_version':'carla-capture-recovery/1','state':'copying',
            'source_run_id':manifest.get('run_id'),'source_files':evidence,'omitted_uncommitted_tail':omitted,
            'source_unchanged':False,'raw_data_verified':False}
    def write(name,value):
        temporary=output/(name+'.tmp')
        temporary.write_text(json.dumps(value,allow_nan=False,ensure_ascii=False,indent=2))
        temporary.replace(output/name)
    try:
        # Copy only capture metadata and committed sensor samples, not unrelated files.
        metadata_names={'calibration.json'}
        for name in manifest.get('files',{}).values():
            if name is None:continue
            if not isinstance(name,str) or Path(name).name!=name or name in ('','.', '..'):
                raise ValueError('Unsafe capture metadata reference')
            if name!='index.json':metadata_names.add(name)
        for name in metadata_names:shutil.copyfile(source/name,output/name)
        for entry in entries:shutil.copytree(source/entry['path'],output/entry['path'])
        recovered={**manifest,'run_id':run_id,'status':'recovery_pending','frame_count':len(entries),
                   'recovery':{'source_run_id':manifest.get('run_id'),'report':'recovery.json',
                               'original_status':manifest['status'],'omitted_uncommitted_tail':omitted}}
        recovered['sensors']={key:{**value,'samples':len(entries)} for key,value in manifest.get('sensors',{}).items()}
        selected_paths={entry['path'] for entry in entries}
        recovered['bytes']=sum(item['bytes'] for name,item in evidence.items()
                               if '/'.join(name.split('/')[:2]) in selected_paths)
        write('index.json',{'frames':entries});write('manifest.json',recovered)
        audit=audit_capture(output,validator,python)
        report['audit']=audit
        if audit['state']!='passed':raise ValueError('Recovery copy did not pass raw sensor validation')
        require_inactive()
        if inventory(source)[0]!=evidence:raise ValueError('Source changed during recovery')
        copied,_=inventory(output)
        for name,item in copied.items():
            if name not in ('manifest.json','index.json') and item!=evidence.get(name):
                raise ValueError('Copied sensor or metadata bytes differ from source')
        report.update(state='recovered',source_unchanged=True,raw_data_verified=True)
        recovered['status']='saved_recovered'
        write('recovery.json',report);write('manifest.json',recovered)
        return output
    except BaseException as exc:
        report.update(state='failed',error=str(exc))
        write('recovery.json',report)
        raise RuntimeError(f'Recovery failed; original untouched; inspect {output}: {exc}') from exc

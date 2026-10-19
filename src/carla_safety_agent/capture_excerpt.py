"""Audited replay excerpts from finalized captures; originals remain untouched."""
import copy
import hashlib
from pathlib import Path
import shutil
import uuid
import zipfile

from .capture_quality import audit_capture
from .data_quality import validate_capture_index
from .scene_store import atomic,finite_number,read_json

MAX_BYTES=4*1024**3
MAX_FRAMES=256


def select_window(entries,manifest,frame,before_s,after_s):
    validate_capture_index(entries,manifest)
    if len(entries)>10000:raise ValueError('Capture index exceeds window selection limit')
    if type(frame) is not int or frame<0:raise ValueError('Select an exact recorded frame')
    if any(not finite_number(v) or not 0<=v<=10 for v in (before_s,after_s)):
        raise ValueError('Window lengths must be 0..10 seconds')
    center=next((entry for entry in entries if entry['frame']==frame),None)
    if center is None:raise ValueError('Selected frame is not recorded')
    low,high=center['timestamp']-before_s,center['timestamp']+after_s
    selected=[entry for entry in entries if low-1e-8<=entry['timestamp']<=high+1e-8]
    if len(selected)>MAX_FRAMES:raise ValueError('Window exceeds 256 saved samples; choose a shorter interval')
    return selected,{'center_frame':frame,'center_timestamp':center['timestamp'],
        'requested_before_s':before_s,'requested_after_s':after_s,
        'first_timestamp':selected[0]['timestamp'],'last_timestamp':selected[-1]['timestamp'],
        'clipped_before':low<entries[0]['timestamp']-1e-8,'clipped_after':high>entries[-1]['timestamp']+1e-8,
        'frame_count':len(selected),'source_frame_count':len(entries),
        'event_claim':'User-selected diagnostic window; not an inferred collision or failure'}


def file_evidence(root,name,max_bytes=512*1024**2):
    relative=Path(name)
    if relative.is_absolute() or '..' in relative.parts:raise ValueError('Unsafe excerpt path')
    path=root/relative
    if any((root/part).is_symlink() for part in [relative,*relative.parents]):
        raise ValueError('Excerpt source contains a symbolic link')
    if not path.is_file() or path.stat().st_size>max_bytes:raise ValueError('Invalid or oversized excerpt file')
    size=0;digest=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):
            size+=len(chunk)
            if size>max_bytes:raise ValueError('Excerpt file grew beyond size limit')
            digest.update(chunk)
    return {'bytes':size,'sha256':digest.hexdigest()}


def create_excerpt(source,output,frame,before_s,after_s,validator,python,require_inactive):
    """Produce a new local replay folder plus ZIP, with audited unchanged raw bytes.

    Caller supplies a unique output directory and proves the source worker is
    inactive. Only selected samples and referenced capture metadata are copied.
    Failure retains unpublished copies for inspection; no source files are edited.
    """
    source=Path(source);output=Path(output)
    if source.is_symlink() or output.exists():raise ValueError('Source link or existing excerpt output refused')
    source=source.resolve()
    if source==output.resolve() or source in output.resolve().parents:raise ValueError('Output must be outside source')
    require_inactive()
    metadata_before={name:file_evidence(source,name) for name in ('manifest.json','index.json')}
    manifest=read_json(source/'manifest.json',max_bytes=8*1024**2)
    if manifest.get('schema_version')!='carla-safety-dataset/0.2' or manifest.get('status') not in ('saved','saved_limit','saved_recovered'):
        raise ValueError('Only finalized unified captures can produce excerpts; recover interrupted captures first')
    if manifest.get('run_id')!=source.name:raise ValueError('Source capture identity mismatch')
    entries=read_json(source/'index.json')['frames']
    selected,window=select_window(entries,manifest,frame,before_s,after_s)
    archive=manifest.get('input_archive')
    if archive not in ('sensor_input.npz','model_input.npz'):raise ValueError('Unknown raw input archive')
    references=manifest.get('files')
    if not isinstance(references,dict) or set(references)-{'calibration','index','scenario','collisions','editor_events','map_projection'}:
        raise ValueError('Unsupported capture metadata references')
    if references.get('calibration')!='calibration.json' or references.get('index')!='index.json':
        raise ValueError('Capture metadata layout differs from unified format')
    for key,name in (('collisions','collisions.json'),('editor_events','editor-events.json')):
        if references.get(key) not in (None,name):raise ValueError('Unsupported event archive layout')
    metadata={'manifest.json','index.json','calibration.json'}
    for kind,name in references.items():
        if name is None:continue
        if kind=='map_projection':
            from .map_projection_archive import read_map_projection
            reference=manifest.get('map_projection')
            read_map_projection(source,reference)
            if name!=reference['path']:raise ValueError('Map projection file reference mismatch')
        if not isinstance(name,str) or Path(name).name!=name or not name.endswith('.xodr' if kind=='map_projection' else '.json'):
            raise ValueError('Unsafe capture metadata reference')
        metadata.add(name)
    sensors=manifest.get('sensors')
    if not isinstance(sensors,dict) or not sensors or not all(isinstance(key,str) and key.isidentifier() and isinstance(value,dict) for key,value in sensors.items()):
        raise ValueError('Invalid capture sensor names')
    allowed={'frame.json',archive,'BEV_POINTS.png'}|{key+suffix for key in sensors for suffix in ('.png','.npy')}
    names=set(metadata)
    for entry in selected:
        folder=source/entry['path']
        if folder.is_symlink() or not folder.is_dir():raise ValueError('Invalid selected sample directory')
        for path in folder.iterdir():
            if path.name not in allowed or not path.is_file():raise ValueError('Unexpected sample file in excerpt')
            names.add(str(path.relative_to(source)))
    evidence={};total=0
    for name in sorted(names):
        evidence[name]=file_evidence(source,name);total+=evidence[name]['bytes']
        if total>MAX_BYTES:raise ValueError('Excerpt exceeds 4 GiB; choose a smaller window')
    if any(evidence[name]!=value for name,value in metadata_before.items()):raise ValueError('Source index or manifest changed during selection')
    if not output.parent.is_dir():raise ValueError('Excerpt output parent is missing')
    if shutil.disk_usage(output.parent).free<2*total+1024**3:raise ValueError('Insufficient space for excerpt and ZIP')
    output.mkdir();dataset=output/('excerpt-'+uuid.uuid4().hex);dataset.mkdir()
    report={'schema_version':'carla-capture-excerpt/1','state':'copying','source_run_id':source.name,
        'execution_id':manifest.get('execution_id'),'window':window,'source_files':evidence,
        'source_unchanged':False,'source_unchanged_scope':'Archived source files only',
        'raw_data_verified':False,'subset_not_full_run':True}
    atomic(output/'report.json',report)
    try:
        originals=output/'source-metadata';originals.mkdir()
        for name in sorted(names):
            if name in metadata:shutil.copyfile(source/name,originals/name)
            if name in ('manifest.json','index.json'):continue
            destination=dataset/name;destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(source/name,destination)
        for name in names-{'manifest.json','index.json'}:
            if file_evidence(dataset,name)!=evidence[name]:raise ValueError('Copied excerpt bytes differ from source')
        for name in metadata:
            if file_evidence(originals,name)!=evidence[name]:raise ValueError('Copied original metadata differs from source')
        # Preserve full event archives in source-metadata; replay only this window.
        if references.get('collisions'):
            from .replay import recorded_collisions
            recorded_collisions(source,entries)  # Validate original event structure.
            collisions=read_json(dataset/'collisions.json')
            original_count=len(collisions['events'])
            collisions['events']=[event for event in collisions['events']
                if window['first_timestamp']<=event['timestamp']<=window['last_timestamp']]
            collisions['excerpt_omitted_events']=original_count-len(collisions['events'])
            collisions['quality_counter_scope']='original capture, not excerpt'
            atomic(dataset/'collisions.json',collisions)
        if references.get('editor_events'):
            from .editor_events import editor_events
            from .replay import replay_editor_events
            replay_editor_events(source.parent,source.name)
            commands=read_json(dataset/'editor-events.json')
            original_events=editor_events(commands['records'],[entry['frame'] for entry in entries],manifest['execution_id'])
            if original_events!=commands.get('events'):raise ValueError('Original editor event index is inconsistent')
            selected_frames={entry['frame'] for entry in selected}
            selected_commands={event['command_id'] for event in original_events
                if event['seek_frame'] in selected_frames or selected[0]['frame']<=event['boundary_frame']<=selected[-1]['frame']}
            commands['records']=[record for record in commands['records'] if record['command_id'] in selected_commands]
            commands['events']=editor_events(commands['records'],[entry['frame'] for entry in selected],manifest['execution_id'])
            commands['excerpt_omitted_records']=len(original_events)-len(commands['records'])
            atomic(dataset/'editor-events.json',commands)
        derived=copy.deepcopy(manifest)
        derived.update(run_id=dataset.name,status='excerpt_pending',frame_count=len(selected),
            excerpt={'source_run_id':source.name,**window,'quality_scope':'Selected samples only; not the full source capture',
                     'source_counters_preserved':True},
            bytes=sum(value['bytes'] for name,value in evidence.items() if name.startswith('samples/')))
        for sensor in derived['sensors'].values():sensor['samples']=len(selected)
        atomic(dataset/'manifest.json',derived);atomic(dataset/'index.json',{'frames':selected})
        audit=audit_capture(dataset,validator,python);report['audit']=audit
        if audit['state']!='passed':raise ValueError('Excerpt raw-data validation did not pass')
        require_inactive()
        if any(file_evidence(source,name)!=value for name,value in evidence.items()):raise ValueError('Source changed during excerpt export')
        derived['status']='saved_excerpt';atomic(dataset/'manifest.json',derived)
        report.update(state='verified',excerpt_run_id=dataset.name,source_unchanged=True,raw_data_verified=True,
            scope='Selected raw samples and derived metadata; original metadata retained; not a complete run or training split')
        atomic(output/'report.json',report)
        bundle=output/'excerpt.zip'
        with zipfile.ZipFile(bundle,'x',compression=zipfile.ZIP_STORED) as target:
            for folder in (dataset,originals):
                for path in sorted(folder.rglob('*')):
                    if path.is_file():target.write(path,str(path.relative_to(output)))
            target.write(output/'report.json','report.json')
        with zipfile.ZipFile(bundle) as target:
            if target.testzip() is not None:raise ValueError('Excerpt ZIP integrity check failed')
        return dataset,bundle,report
    except BaseException as exc:
        report.update(state='failed',error=str(exc));atomic(output/'report.json',report)
        raise

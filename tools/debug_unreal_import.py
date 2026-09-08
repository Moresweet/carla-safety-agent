"""Explicit new-asset import under GDB; no automatic registry update."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import uuid

from carla_safety_agent.blender_pipeline import BlenderPipeline


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('fbx',type=Path)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    assert args.fbx.is_file()
    attempt=uuid.uuid4().hex
    folder=root/'runs/validation'/('debug-import-'+attempt);folder.mkdir(parents=True)
    request=folder/'request.json';result=folder/'result.json';log=folder/'gdb.log'
    request.write_text(json.dumps({'asset_id':'CSA_DebugImport_'+attempt[:10],
        'fbx_path':str(args.fbx.resolve()),'result_path':str(result),
        'color':[.15,.55,.85,1.0],'roughness':.45}))
    pipeline=BlenderPipeline(root)
    command=['gdb','--batch','-ex','set debuginfod enabled off','-ex','set breakpoint pending on',
        '-ex','set print thread-events off','-ex','break __cxa_pure_virtual','-ex','run',
        '-ex','bt 35','--args',pipeline.ue_editor,pipeline.carla_project,'-run=pythonscript',
        '-script='+str(pipeline.importer),'-unattended','-nop4','-nosplash','-nullrhi']
    print(json.dumps({'folder':str(folder),'asset_name':'CSA_DebugImport_'+attempt[:10]}),flush=True)
    with log.open('w') as stream:
        completed=subprocess.run(command,env={**os.environ,'CSA_UNREAL_IMPORT_REQUEST':str(request)},
            stdout=stream,stderr=subprocess.STDOUT,timeout=600)
    print(json.dumps({'debugger_returncode':completed.returncode,'asset_result_written':result.exists(),
                     'log':str(log),'registry_modified':False}),flush=True)
    print(log.read_text()[-18000:],flush=True)


if __name__=='__main__':main()

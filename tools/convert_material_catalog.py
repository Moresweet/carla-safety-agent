"""Convert only successfully exported slots; keep unsupported status explicit."""
import json
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = Path(sys.argv[1]).resolve()
catalog = json.loads(source.read_text())
for entries in catalog['actors'].values():
    for entry in entries:
        if entry['status'] != 'fbx_exported': continue
        for slot in entry['slots']:
            target = source.parent/f"{entry['mesh_key']}-slot-{slot['slot']}.json"
            result = subprocess.run([str(root/'.runtime/fbx_mesh_to_json'), entry['fbx'], str(target), str(slot['slot'])], capture_output=True, text=True)
            if result.returncode:
                slot.update(status='no_exported_uv_triangles', error=result.stderr[-1000:])
            else:
                mesh = json.loads(target.read_text())
                slot.update(status='uv0_ready', mesh_file=target.name, triangles=mesh['triangleCount'])
result_path = source.parent/'preview-catalog.json'
result_path.write_text(json.dumps(catalog, indent=2))
print(result_path)

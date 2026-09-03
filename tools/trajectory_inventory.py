#!/usr/bin/env python3
"""Inspect local highD/NGSIM archives and installed ZhiLing CARLA maps."""
import json
from pathlib import Path
from zipfile import ZipFile

DATA = Path("/home/moresweet/Data")
MAPS = Path("/home/moresweet/carla/Unreal/CarlaUE4/Content/ZhiLing/Plugin_Import/Maps")

def archive(path: Path) -> dict:
    with ZipFile(path) as bundle:
        names = bundle.namelist()
    return {"path": str(path), "bytes": path.stat().st_size, "members": len(names),
            "csv": [n for n in names if n.lower().endswith(".csv")],
            "nested_zip": [n for n in names if n.lower().endswith(".zip")]}

def main() -> None:
    sources = [DATA / "higd/highd-dataset-v1.0.zip", *sorted((DATA / "ngsim").glob("*.zip"))]
    print(json.dumps({"sources": [archive(p) for p in sources if p.is_file()],
                      "missing_sources": [str(p) for p in sources if not p.is_file()],
                      "installed_maps": sorted(p.stem for p in MAPS.glob("*.umap")),
                      "installed_opendrive": sorted(p.name for p in (MAPS / "OpenDrive").glob("*.xodr"))}, indent=2))

if __name__ == "__main__":
    main()

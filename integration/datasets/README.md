# highD and NGSIM integration

The repository does not copy the licensed multi-gigabyte datasets or UE assets. It records their expected host locations and supplies repeatable installers and inventory tools.

Run `scripts/install_zhiling_maps.sh`, restart UE4Editor, then select a map, for example:

```bash
CARLA_MAP=/Game/ZhiLing/Plugin_Import/Maps/HighD_1 scripts/start_surface_studio.sh
CARLA_MAP=/Game/ZhiLing/Plugin_Import/Maps/NGSIM_I-80_20260427 scripts/start_surface_studio.sh
```

Installed maps are `HighD_1` through `HighD_6`, plus NGSIM I-80, US-101, Lankershim Boulevard, and Peachtree Street. Each package includes OpenDRIVE and original materials/geometries.

Raw archives are read from `/home/moresweet/Data/higd` and `/home/moresweet/Data/ngsim`. Ozone is the schema reference: source coordinates are converted to metres while frame, class, size, lane and velocity are retained. Simulator replay additionally needs a per-map rigid calibration because neither Ozone nor the raw datasets defines CARLA world coordinates. This transform must be calibrated against each supplied map/OpenDRIVE, not guessed.

Use `tools/trajectory_inventory.py` to verify source archives and installed map assets.

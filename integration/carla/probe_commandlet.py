"""Read-only commandlet probe; optionally loads one asset, never saves it."""
import os
import unreal

asset_path = os.environ.get('CSA_PROBE_ASSET')
if asset_path:
    asset = unreal.load_asset(asset_path)
    if not asset:
        raise RuntimeError('Probe asset could not be loaded')
    unreal.log('CSA_COMMANDLET_ASSET_LOADED ' + asset.get_path_name())
unreal.log('CSA_COMMANDLET_PROBE_COMPLETED')

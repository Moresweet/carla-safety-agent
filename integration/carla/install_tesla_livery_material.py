import unreal

material_path = '/Game/Carla/Static/Car/4Wheeled/Tesla/Materials'
material_name = 'M_CarlaLiveryRuntime'
material = unreal.load_asset(material_path + '/' + material_name)
if not material:
    material = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        material_name, material_path, unreal.Material, unreal.MaterialFactoryNew())
    sample = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionTextureSampleParameter2D, -300, 0)
    sample.set_editor_property('parameter_name', 'LiveryTexture')
    sample.set_editor_property('texture', unreal.load_asset(
        material_path + '/M_Tesla_Bodywork_d_a'))
    unreal.MaterialEditingLibrary.connect_material_property(
        sample, 'RGB', unreal.MaterialProperty.MP_BASE_COLOR)
    roughness = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionConstant, -300, 180)
    roughness.set_editor_property('r', 0.32)
    unreal.MaterialEditingLibrary.connect_material_property(
        roughness, '', unreal.MaterialProperty.MP_ROUGHNESS)
    metallic = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionConstant, -300, 300)
    metallic.set_editor_property('r', 0.15)
    unreal.MaterialEditingLibrary.connect_material_property(
        metallic, '', unreal.MaterialProperty.MP_METALLIC)
    material.set_editor_property('used_with_skeletal_mesh', True)
    unreal.MaterialEditingLibrary.recompile_material(material)
    unreal.EditorAssetLibrary.save_loaded_asset(material)

mesh = unreal.load_asset('/Game/Carla/Static/Car/4Wheeled/Tesla/SM_TeslaM3_v2')
slots = mesh.get_editor_property('materials')
slots[5].set_editor_property('material_interface', material)
mesh.set_editor_property('materials', slots)
unreal.EditorAssetLibrary.save_loaded_asset(mesh)

exterior = unreal.load_asset(material_path + '/MI_CarExterior_TeslaM3')
exterior.set_editor_property('parent', material)
exterior.modify(True)
unreal.EditorAssetLibrary.save_loaded_asset(exterior, False)
unreal.log_warning('TESLA_LIVERY_INSTALLED ' + material.get_path_name())

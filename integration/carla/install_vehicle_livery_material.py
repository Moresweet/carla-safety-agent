"""Create the shared UV0 skeletal vehicle livery material."""
import unreal

PATH = "/Game/Carla/Static/GenericMaterials"
NAME = "M_CarlaVehicleLiveryRuntime"
material = unreal.load_asset(PATH + "/" + NAME)
if not material:
    material = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        NAME, PATH, unreal.Material, unreal.MaterialFactoryNew())
material.set_editor_property("used_with_skeletal_mesh", True)
unreal.MaterialEditingLibrary.delete_all_material_expressions(material)
coordinates = unreal.MaterialEditingLibrary.create_material_expression(
    material, unreal.MaterialExpressionTextureCoordinate, -400, 0)
sample = unreal.MaterialEditingLibrary.create_material_expression(
    material, unreal.MaterialExpressionTextureSampleParameter2D, -150, 0)
sample.set_editor_property("parameter_name", "Diffuse")
sample.set_editor_property("texture", unreal.load_asset(
    "/Game/Carla/Static/GenericMaterials/Asphalt/Textures/Asphalt01/T_Asphalt01_d"))
unreal.MaterialEditingLibrary.connect_material_expressions(coordinates, "", sample, "UVs")
unreal.MaterialEditingLibrary.connect_material_property(
    sample, "RGB", unreal.MaterialProperty.MP_BASE_COLOR)
roughness = unreal.MaterialEditingLibrary.create_material_expression(
    material, unreal.MaterialExpressionConstant, 100, 180)
roughness.set_editor_property("r", 0.58)
unreal.MaterialEditingLibrary.connect_material_property(
    roughness, "", unreal.MaterialProperty.MP_ROUGHNESS)
unreal.MaterialEditingLibrary.recompile_material(material)
unreal.EditorAssetLibrary.save_loaded_asset(material, False)
unreal.log_warning("CARLA_VEHICLE_LIVERY_MATERIAL_INSTALLED " + material.get_path_name())

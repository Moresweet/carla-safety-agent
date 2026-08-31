"""Create the runtime-replaceable wall material for verified buildings."""
import unreal

PATH = "/Game/Carla/Static/Building/Materials"
NAME = "M_CarlaBuildingRuntime"
material = unreal.load_asset(PATH + "/" + NAME)
if not material:
    material = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        NAME, PATH, unreal.Material, unreal.MaterialFactoryNew())
unreal.MaterialEditingLibrary.delete_all_material_expressions(material)
coordinates = unreal.MaterialEditingLibrary.create_material_expression(
    material, unreal.MaterialExpressionTextureCoordinate, -400, 0)
sample = unreal.MaterialEditingLibrary.create_material_expression(
    material, unreal.MaterialExpressionTextureSampleParameter2D, -150, 0)
sample.set_editor_property("parameter_name", "Diffuse")
sample.set_editor_property("texture", unreal.load_asset(
    "/Game/Carla/Static/GenericMaterials/00_MastersOpt/Characters/GenericTextures/Fabrics/T_FabricCotton_D"))
if not sample.get_editor_property("texture"):
    sample.set_editor_property("texture", unreal.load_asset(
        "/Game/Carla/Static/GenericMaterials/Asphalt/Textures/Asphalt01/T_Asphalt01_d"))
if not unreal.MaterialEditingLibrary.connect_material_expressions(coordinates, "", sample, "UVs"):
    raise RuntimeError("Failed building texture coordinate connection")
unreal.MaterialEditingLibrary.connect_material_property(
    sample, "RGB", unreal.MaterialProperty.MP_BASE_COLOR)
roughness = unreal.MaterialEditingLibrary.create_material_expression(
    material, unreal.MaterialExpressionConstant, 100, 180)
roughness.set_editor_property("r", 0.72)
unreal.MaterialEditingLibrary.connect_material_property(
    roughness, "", unreal.MaterialProperty.MP_ROUGHNESS)
unreal.MaterialEditingLibrary.recompile_material(material)
unreal.EditorAssetLibrary.save_loaded_asset(material, False)
unreal.log_warning("CARLA_BUILDING_RUNTIME_MATERIAL_INSTALLED " + material.get_path_name())

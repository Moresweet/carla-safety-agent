"""Install a non-overlapping local-space projection material for the Tesla."""
import unreal

path = '/Game/Carla/Static/Car/4Wheeled/Tesla/Materials'
name = 'M_CarlaLiveryRuntime'
material = unreal.load_asset(path + '/' + name)
if not material:
    material = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, path, unreal.Material, unreal.MaterialFactoryNew())
unreal.MaterialEditingLibrary.delete_all_material_expressions(material)
make = lambda cls, x, y: unreal.MaterialEditingLibrary.create_material_expression(material, cls, x, y)
def wire(source, output_name, target, input_name):
    if not unreal.MaterialEditingLibrary.connect_material_expressions(
            source, output_name, target, input_name):
        raise RuntimeError('Failed material connection: {}.{} -> {}.{}'.format(
            source.get_name(), output_name, target.get_name(), input_name))

world_position = make(unreal.MaterialExpressionWorldPosition, -1700, -200)
position = make(unreal.MaterialExpressionTransformPosition, -1500, -200)
position.set_editor_property('transform_source_type', unreal.MaterialPositionTransformSource.TRANSFORMPOSSOURCE_WORLD)
position.set_editor_property('transform_type', unreal.MaterialPositionTransformSource.TRANSFORMPOSSOURCE_LOCAL)
wire(world_position, '', position, '')
bounds = make(unreal.MaterialExpressionPreSkinnedLocalBounds, -1500, 100)
subtract = make(unreal.MaterialExpressionSubtract, -1300, -150)
divide = make(unreal.MaterialExpressionDivide, -1100, -150)
wire(position, '', subtract, 'A'); wire(bounds, 'Min', subtract, 'B')
wire(subtract, '', divide, 'A'); wire(bounds, 'Extents', divide, 'B')

def mask(channel, x, y):
    node = make(unreal.MaterialExpressionComponentMask, x, y)
    node.set_editor_property('r', channel == 'r'); node.set_editor_property('g', channel == 'g'); node.set_editor_property('b', channel == 'b')
    wire(divide, '', node, '')
    return node

nx, ny, nz = mask('r', -900, -300), mask('g', -900, -150), mask('b', -900, 0)
one_x = make(unreal.MaterialExpressionOneMinus, -700, -300); wire(nx, '', one_x, '')
one_z = make(unreal.MaterialExpressionOneMinus, -700, 0); wire(nz, '', one_z, '')

def packed_uv(horizontal, vertical, offset, y):
    third = make(unreal.MaterialExpressionMultiply, -500, y); third.set_editor_property('const_b', 1.0 / 3.0); wire(horizontal, '', third, 'A')
    shifted = third
    if offset:
        shifted = make(unreal.MaterialExpressionAdd, -320, y); shifted.set_editor_property('const_b', offset / 3.0); wire(third, '', shifted, 'A')
    append = make(unreal.MaterialExpressionAppendVector, -120, y); wire(shifted, '', append, 'A'); wire(vertical, '', append, 'B')
    return append

top_uv = packed_uv(ny, one_x, 0, -350)
left_uv = packed_uv(nx, one_z, 1, -100)
right_uv = packed_uv(one_x, one_z, 2, 150)
side_choice = make(unreal.MaterialExpressionIf, 100, 50); side_choice.set_editor_property('const_b', 0.5)
wire(ny, '', side_choice, 'A'); wire(right_uv, '', side_choice, 'A > B'); wire(left_uv, '', side_choice, 'A < B')

world_normal = make(unreal.MaterialExpressionPixelNormalWS, -120, 360)
local_normal = make(unreal.MaterialExpressionTransform, 80, 360)
local_normal.set_editor_property('transform_source_type', unreal.MaterialVectorCoordTransformSource.TRANSFORMSOURCE_WORLD)
local_normal.set_editor_property('transform_type', unreal.MaterialVectorCoordTransform.TRANSFORM_LOCAL)
wire(world_normal, '', local_normal, '')
normal_y = make(unreal.MaterialExpressionComponentMask, 280, 330); normal_y.set_editor_property('r', False); normal_y.set_editor_property('g', True); normal_y.set_editor_property('b', False); wire(local_normal, '', normal_y, '')
normal_z = make(unreal.MaterialExpressionComponentMask, 280, 430); normal_z.set_editor_property('r', False); normal_z.set_editor_property('g', False); normal_z.set_editor_property('b', True); wire(local_normal, '', normal_z, '')
abs_y = make(unreal.MaterialExpressionAbs, 450, 330); wire(normal_y, '', abs_y, '')
abs_z = make(unreal.MaterialExpressionAbs, 450, 430); wire(normal_z, '', abs_z, '')
projection = make(unreal.MaterialExpressionIf, 620, 360)
wire(abs_z, '', projection, 'A'); wire(abs_y, '', projection, 'B'); wire(top_uv, '', projection, 'A > B'); wire(side_choice, '', projection, 'A < B')

sample = make(unreal.MaterialExpressionTextureSampleParameter2D, 820, 20)
sample.set_editor_property('parameter_name', 'LiveryTexture'); sample.set_editor_property('texture', unreal.load_asset(path + '/M_Tesla_Bodywork_d_a')); wire(projection, '', sample, 'UVs')
base = make(unreal.MaterialExpressionVectorParameter, 820, 260); base.set_editor_property('parameter_name', 'CarColor'); base.set_editor_property('default_value', unreal.LinearColor(0.8, 0.8, 0.8, 1.0))
blend = make(unreal.MaterialExpressionLinearInterpolate, 1080, 100); wire(base, '', blend, 'A'); wire(sample, 'RGB', blend, 'B'); wire(sample, 'A', blend, 'Alpha')
unreal.MaterialEditingLibrary.connect_material_property(blend, '', unreal.MaterialProperty.MP_BASE_COLOR)
roughness = make(unreal.MaterialExpressionConstant, 1080, 300); roughness.set_editor_property('r', 0.32)
metallic = make(unreal.MaterialExpressionConstant, 1080, 400); metallic.set_editor_property('r', 0.15)
unreal.MaterialEditingLibrary.connect_material_property(roughness, '', unreal.MaterialProperty.MP_ROUGHNESS); unreal.MaterialEditingLibrary.connect_material_property(metallic, '', unreal.MaterialProperty.MP_METALLIC)
material.set_editor_property('used_with_skeletal_mesh', True); unreal.MaterialEditingLibrary.recompile_material(material); unreal.EditorAssetLibrary.save_loaded_asset(material, False)

mesh = unreal.load_asset('/Game/Carla/Static/Car/4Wheeled/Tesla/SM_TeslaM3_v2'); slots = mesh.get_editor_property('materials'); slots[5].set_editor_property('material_interface', material); mesh.set_editor_property('materials', slots); unreal.EditorAssetLibrary.save_loaded_asset(mesh, False)
exterior = unreal.load_asset(path + '/MI_CarExterior_TeslaM3'); exterior.set_editor_property('parent', material); exterior.modify(True); unreal.EditorAssetLibrary.save_loaded_asset(exterior, False)
unreal.log_warning('TESLA_PROJECTED_LIVERY_INSTALLED ' + material.get_path_name())

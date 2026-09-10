# Source UV preview contract

The FBX exporter in this local UE 4.26 build writes `(u, 1-v)`
(`FbxSkeletalMeshExport.cpp`, `UVDiffuseLayer`). Our
`tools/fbx_mesh_to_json.cpp` converter restores `(u, v)`. The JSON therefore
already uses Unreal UV0's top-left image convention, also used by bridge
`decode_texture` when assigning pixels to CARLA textures.

For `useSourceUV` previews, upload the canvas without WebGL Y flipping and
bake projection triangles to `(u * width, v * height)`. Do not apply another
`1-v`. The Tesla procedural three-panel path is separate and retains its
existing upload convention. Repeated source UVs are not clamped by this helper.

`tools/test_preview_uv.mjs` covers this contract and portrait projection fit.
`tools/browser_reviewed_models.mjs --uv-convention` additionally samples four
asymmetric canvas colors through actual WebGL using the production helper.
Neither test alone establishes geometry/material fidelity in Unreal.

## Supported pedestrian export

The verified `walker.pedestrian.0001` blueprint uses `SK_Female`; runtime
replacement is limited to material slot 14, `Cloths03_PANTS`. Its exported
preview contains 2,799 triangles in the source bind pose. It is not a preview
of current animation, the whole outfit, skin, hair, or other pedestrian types.

Recreate the local preview with the existing native UE and FBX converter:

1. Choose a fresh output directory and set `CSA_PEDESTRIAN_UV_OUTPUT` to it.
2. Run `UE4Editor <CarlaUE4.uproject> -run=pythonscript
   -script=<repo>/integration/carla/export_verified_pedestrian_uv.py
   -nullrhi -unattended -nosplash -nosound -stdout
   -abslog=<output>/unreal.log`.
3. Check `manifest.json`: successful export, expected class, mesh and slot 14.
4. Run the existing compiled `fbx_mesh_to_json <output>/walker.fbx
   <repo>/tools/livery-designer/public/pedestrians/walker-pedestrian-0001-slot14.json 14`.
5. Run mesh validation and the opt-in `tools/regression_pedestrian_uv.py
   --node <node24>` with the local studio idle, then inspect saved images.

The export does not save maps or assets. Generated FBX and mesh JSON are local
artifacts excluded from Git; the tracked catalog is not evidence that these
files exist on a new machine. Missing preview files are reported by the UI.

## Visual verification and capture isolation

The pedestrian regression owns two newly spawned walkers, edits only one
through the browser, captures an untouched control, and restores the previous
camera after deleting its own actors. Red-top/yellow-left calibration markers
allow orientation comparison. It does not change maps or start a model.

Native `DebugHelper.draw_box` selection shapes appeared as black blocks in
RGB previews on this build. An unchanged textured actor captured after the
eight-second debug lifetime no longer had those blocks. Focus operations now
move the camera without drawing native debug geometry; selection feedback
stays in the web UI. This avoids injecting UI markers into sensor imagery.

The source preview does not reproduce Unreal lighting, normals, material
layers or animation. Additional vehicle and environment visual regression is
required whenever the shared source-UV upload convention changes.
# 预览故障隔离增量

CarPreview 对无效几何、WebGL不可用、着色器编译/链接失败显示局部错误；网格切换或卸载时释放顶点/UV缓冲、程序与纹理，编译失败也释放已创建的着色器。此处不保证所有浏览器上下文丢失或其他编辑组件的异常均已覆盖。

真实浏览器无WebGL注入通过，纹理画布仍正常：browser-models-3b1b560c-b90a-4299-8ce6-66d0f78037b2/material-uv.png。正常WebGL回归通过且截图已查看：browser-models-05de0eff-f2cc-40ee-ba76-23730e777f25/material-uv.png。测试先验证注入生效；导航等待服务端页面完成交互初始化，失败保存异常、正文与截图，不重试写操作。

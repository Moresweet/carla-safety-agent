# 本机场景与 Blender 源资产迁移

当前提供 CLI；完整项目一键迁移仍开发中。以下命令在仓库根目录运行，
`PROJECT`、`SCENE`、`OUTPUT` 等需替换为实际路径或 ID。

## 导出

```bash
PYTHONPATH=src python3 tools/project_bundle.py export \
  --project PROJECT --scene SCENE --output OUTPUT.zip \
  --include-material-previews \
  --generated-asset generated.prop.MODEL=SOURCE_PACKAGE.zip
```

`--generated-asset` 可重复。启用后必须准确覆盖所选场景全部历史版本引用的
`generated.prop.*` ID，不接收无引用的资产。源包由 `tools/blender_package.py export`
创建，含 FBX、可选 Blend/GLB/纹理及显式材质参数。绑定是操作者明确选择的对应关系，
校验和只能验证字节完整性，不能自动证明所选源包就是该模型的原始文件。

不加此选项仍可导出旧式场景包，但不会携带生成模型源文件。
包内包含场景历史、引用纹理及可选 UV 预览，不包含 Unreal `.uasset`、模型权重、
采集数据、执行记录或程序运行环境。嵌套资产包也受总解压大小限制。

## 检查和隔离导入

```bash
PYTHONPATH=src python3 tools/project_bundle.py inspect OUTPUT.zip
PYTHONPATH=src python3 tools/project_bundle.py import OUTPUT.zip --destination-parent PARENT
PYTHONPATH=src python3 tools/project_bundle.py prepare-assets OUTPUT.zip --project TARGET_PROJECT
```

`import` 创建独立 `carla-project-*` 目录，不覆盖现有项目。
`prepare-assets` 将全部已校验源包准备为目标项目的 Blender 任务，输出原模型 ID、
新任务 ID 和建议导入名，重写本机文件路径。它不启动 Blender/Unreal，不写资产注册表，
不修改运行世界；重复调用会创建新任务。磁盘故障时已准备的任务可能保留，暂不提供批量回滚。

随后显式执行目标 Unreal 导入注册：

```bash
PYTHONPATH=src python3 tools/register_bundle_assets.py OUTPUT.zip \
  --project TARGET_INSTALLED_PROJECT --output REMAPPED.zip --execute-unreal-import
```

目标必须有本项目代码与可用的Unreal导入脚本。该操作采用全新唯一名称导入，不覆盖
目标同名资产，并生成替换了模型引用的新场景包；原包不改动，场景稳定对象ID保留。
只有退出码0且结果身份符合请求才注册成功。同项目导入通过文件锁串行化。
每次操作在`.runtime/blender-assets/migrations/操作ID/report.json`留存进度。
失败保留已导入资产及任务，并标记needs_attention，不自动重试或回滚已有资产；
再次执行是一次新操作，不是断点续跑。输出包写入失败也可能留下部分文件，需检查报告。

将成功生成的REMAPPED.zip交给现有stage及场景恢复流程，仍需目标同地图。
当前CLI不会自动修改运行世界或启动目标CARLA，完整图形界面向导和跨机验收仍未完成。

不要覆盖旧资产或手改 ID 跳过冲突。当前恢复接口只支持目标同地图，且要求目标注册表
已能解析对应生成 ID；源文件在包内并不代表模型已经能在目标 CARLA 中生成。
`doctor` 对生成 ID 报告注册/网格状态未验证，而不是用原生 Blueprint 列表误判。

## 当前验证范围

已覆盖真实生成护栏随场景打包、隔离导入后源文件字节一致、准备任务不执行/不注册，
以及在已有同一资产注册的原 CARLA 中删除后恢复、稳定 ID 保留和重复恢复无副本。
这不等同于另一台机器上的 Unreal 导入或全项目迁移验收。

# 本机场景与 Blender 源资产迁移

当前提供图形项目包导出/隔离导入、显式Unreal源资产注册与同地图实景恢复，详见[项目包界面](PROJECT_BUNDLE_UI.md)。完整跨机环境安装与验收仍开发中。以下CLI命令在仓库根目录运行，
`PROJECT`、`SCENE`、`OUTPUT` 等需替换为实际路径或 ID。

程序、测试、ROS工具与引擎补丁可单独导出为[源码快照包](SOURCE_BUNDLE.md)，不依赖聊天记录。
它锁定本地Git提交，不能代替场景/模型/运行环境迁移，也不会自动推送GitHub。

## 目标机器路径预检

启动与维护脚本现在共用 `scripts/studio_paths.sh`。迁移前显式配置下面的路径；
默认值只是开发机兼容值，不意味着目标机器已经安装依赖：

```bash
export CARLA_ROOT=/new/path/to/carla
export UE4_ROOT=/new/path/to/UnrealEngine_4.26
export E2E_ROOT=/new/path/to/e2e
export CARLA_PYTHONPATH=/new/path/to/native/python/site-packages
export UNIAD_PYTHON=/new/path/to/model/environment/bin/python
export BLENDER_BIN=/new/path/to/blender
source scripts/studio_paths.sh
PYTHONPATH=src python3 tools/runtime_paths_doctor.py
```

需要时还可单独覆盖 `UE4_EDITOR`、`UE4_EDITOR_CMD`、`CARLA_PROJECT`。
原生维护重启会在任何保存/停止服务之前运行 native 范围预检；缺少文件就拒绝重启。
检查只读取上述指定路径，不扫描其他目录、不执行对应程序、不访问仿真、不加载模型。
`paths_present=true` **仅表示路径/可执行权限存在**；`runtime_verified`始终为false。
Python ABI、CUDA、引擎补丁构建、模型指纹/推理和场景恢复仍须分别验收。
原生桥接Python目录与模型Python环境可能不同，切勿把Python3.14的CARLA扩展加入Python3.10模型环境。

## 导出命令

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

## 可选模型文件指纹

先生成相对路径的模型引用清单，再随场景包携带。只读取文件计算校验和，不加载
checkpoint、不执行配置；权重本体不进入项目包。示例：

```bash
PYTHONPATH=src python3 tools/runtime_reference.py export \
  --zoo /path/to/Bench2DriveZoo --tcp-zoo /path/to/Bench2DriveZoo-tcp-admlp \
  --model vad --model tcp --output model-reference.json
PYTHONPATH=src python3 tools/project_bundle.py export \
  --project PROJECT --scene SCENE --output OUTPUT.zip \
  --runtime-reference model-reference.json
```

导入后显式指定新机器目录：

```bash
PYTHONPATH=src python3 tools/runtime_reference.py verify \
  TARGET/data/runtime/reference.json \
  --root zoo=/new/path/to/Bench2DriveZoo \
  --root tcp_zoo=/new/path/to/Bench2DriveZoo-tcp-admlp
```

缺目录、缺文件、大小/校验和不符分别报告，失败退出非零。路径必须在所指定根目录内，
拒绝路径穿越和越界符号链接。输出文件不覆盖。清单只覆盖显式选择模型在目录中声明的
adapter、checkpoint及可选config，不包括传递导入、工作室包装器、完整Python/CUDA环境。
同样的文件指纹不是推理兼容性证明；场景doctor对模型仍报告未检查，不冒充已运行。

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
当前CLI不会自动修改运行世界或启动目标CARLA。图形界面已有独立确认的源注册→新包→恢复链路；跨机验收仍未完成。

不要覆盖旧资产或手改 ID 跳过冲突。当前恢复接口只支持目标同地图，且要求目标注册表
已能解析对应生成 ID；源文件在包内并不代表模型已经能在目标 CARLA 中生成。
`doctor` 对生成 ID 报告注册/网格状态未验证，而不是用原生 Blueprint 列表误判。

## 当前验证范围

已覆盖真实生成护栏随场景打包、隔离导入后源文件字节一致、准备任务不执行/不注册，
以及在已有同一资产注册的原 CARLA 中删除后恢复、稳定 ID 保留和重复恢复无副本。
这不等同于另一台机器上的 Unreal 导入或全项目迁移验收。

后续本机GUI端到端证据：browser-registered-restore-dd86fbab310142408c84e50845694a5b，已完成源资产重新导入、唯一Blueprint引用新包、单独确认实景生成及mesh_path核验，测试对象清理。原生资产和本机环境并不因此自动出现在另一台机器；迁移时仍须分别准备源码、引擎补丁/构建、Python/CUDA、模型文件与采集数据。

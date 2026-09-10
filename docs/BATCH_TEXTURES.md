# 本机精确材质槽 A/B 批测

支持规则驾驶及生成场景的五个真实模型适配器。范围是当前地图、已导出 UV0 的环境对象 component/slot；不是任意车辆或行人皮肤，也不会为纹理测试自动切换地图。

## 准备与执行

1. 在材质编辑器保存候选纹理，并保存候选场景版本；从该版本 `environment_materials` 读取目标、组件、槽号和纹理 SHA-256。PNG 必须仍在项目的内容寻址纹理库中。
2. 恢复你要使用的基线场景。空纹理配置 `{}` 表示保持**测试开始时的编辑状态**，不表示出厂材质。若基线已是候选纹理，两组不会产生该槽的视觉差异。
3. 批量矩阵的 `textures` 中放入两个不同 ID：基线的 `configuration` 为 `{}`；候选的 `configuration` 为 `{"environment_materials": [...]}`，列表使用第一步的原始记录，不手写推测对象名或哈希。
4. 其余模型、场景、天气、种子相同，确认后后台串行运行。查看每次执行的真实采集，再按纹理轴比较指标。目标不在路线/摄像头视野中时，即使应用成功，也不能据此分析视觉影响。

## 恢复与审计

- 候选配置写入不可变场景及其 SHA-256，同时随采集归档；执行日志保存应用前与目标材质集合、地图和 episode。
- 先校验全部槽位及纹理引用，再持久保存恢复信息，最后修改世界、启动进程。仅覆盖候选指定槽，其他已有编辑保持不变。
- 正常结束或启动失败都会恢复原槽位。RPC 结果不确定时，恢复使用持久记录包含所有可能已修改的槽，而不只依赖最后一次成功写入的本地覆盖表。
- 子进程仍存活时不抢先恢复。恢复失败保留 `recovering`，禁止后续任务；需要排查后使用现有会话恢复功能。episode 改变时拒绝写入另一个世界，不自动加载旧地图。
- 恢复记录和本地材质表不是 GPU 画面的独立证明；应检查实际摄像头帧。短 A/B 对比是描述性指标差异，不代表统计显著性或驾驶安全结论。

可重复回归：`PYTHONPATH=src:<CARLA PythonAPI 路径> python3 tools/regression_batch_textures.py --model vad --target Road_Road_Town04_320`。脚本使用项目已有 Town04 道路校准纹理，先确认文件存在；不满足前提就拒绝执行。原默认目标 Road_Road_Town04_1 不在默认出生点视野中，不能将接口回归当成视觉验收。

补充导出请求见 `integration/carla/material-export-town04-route.json`，包含默认路线附近四段道路。使用独立 Unreal 只读命令行执行 `export_scene_materials.py`，然后运行 `convert_material_catalog.py`；最后用 `PYTHONPATH=src python3 tools/merge_material_catalog.py <新目录>/preview-catalog.json --data-root data` 合入。合并先校验真实三角网格、UV 数据及已有定义冲突，最后原子更新目录；不覆盖不同内容的已有目标，不修改世界。文件写入阶段的磁盘故障可能留下尚未引用的预览文件，原目录仍保留。

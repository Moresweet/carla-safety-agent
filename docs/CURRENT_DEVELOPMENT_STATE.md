# 继续开发入口

更新日期：2026-09-10。本文件用于换聊天后的定位，不替代详细开发计划，也不表示项目整体完成。

## 项目位置与约束

- 仓库：`/home/moresweet/Documents/ChatGPT/SafeAgent/carla-safety-agent`。
- 当前按本机模式开发；网页3000、桥接8765、CARLA2000。不要按旧README目录或Docker路线启动。
- 原生CARLA位于`/home/moresweet/carla`，UE4.26位于`/home/moresweet/UnrealEngine_4.26`；这些不是场景ZIP自动携带的依赖。
- 原生Python3.14与模型Python3.10不能混用CARLA扩展路径。模型环境为`/home/moresweet/Data/e2e/miniconda3/envs/uniad-cu128/bin/python`。
- 不删除现有采集数据、生成资产、模型权重或外部引擎脏工作树。运行矩阵期间冻结其加载的代码，不重启服务。

## 本轮新增并完成实测的功能

- `89a5d51`：工作台新增Audi A2车身槽纹理版本，桥接重启、撤销/重做、稳定ID重建与项目包恢复；其他对象隔离。
- `cf7f548`：共享UV修正后的道路网页/原生复测，3D预览有界缩放和重置。
- `a21bba1`、`0c944a9`：中断录制复制恢复，原件hash保持、未提交尾帧明确排除、完整原始数据校验、网页确认/回放/复检；修复重复组件key。
- `52f1c23`：Unreal子进程继承导入互斥锁，Linux子进程及实际原生导入回归通过。
- `25e4caa`：项目包源资产显式注册、新Blueprint引用包、单独确认实景恢复，全GUI链路及真实网格生成通过。
- `5d1c9b3`：未知动态对象来源不再猜成场景原有，筛选标签与紧凑布局经过原生重启和浏览器验证。
- `7870c1f`：行人0001裤装精确槽纹理版本，原生引擎编译、场景重建和网页项目包恢复通过。

截至上述提交：695项Python测试、TypeScript与生产构建通过。其后五模型短闭环矩阵已全部通过，报告`runs/validation/reviewed-models-a13499d155104ec19eb591a75e553a41.json`；VAD/TCP/UniAD-Tiny/UniAD-Base各20帧，AD-MLP60帧，原始采集、预测空间契约和退出清理均通过，五者网页回放截图均已查看。这不是长时间稳定性或驾驶质量认证。

行人引擎增量后另跑VAD/TCP各20帧，报告`reviewed-models-6bc0a719b9534e47ba59246c1c593948.json`，两者原始数据、空间预测、清理及网页回放均通过。当前原生episode为12684580936238673218；PID需运行时重新确认。最新单测708项通过（含调度线程启动失败保护）；具体提交和原生异常矩阵见开发计划尾部。

详细证据入口：

- [完整计划与按时间记录](DEVELOPMENT_PLAN.md)
- [纹理版本边界](ACTOR_MATERIAL_VERSIONS.md)、[真实UV与视觉证据](SOURCE_UV_PREVIEW.md)
- [场景历史完整性与写入失败边界](SCENE_STORAGE_INTEGRITY.md)：该增量后完整Python测试730项通过。
- [中断采集恢复](CAPTURE_RECOVERY.md)
- [项目包界面](PROJECT_BUNDLE_UI.md)、[迁移命令与不包含项](PROJECT_MIGRATION.md)
- [预测空间契约](PREDICTION_SPATIAL_CONTRACT.md)

## 尚不能宣称完成的范围

- 场景恢复目前仅同地图；跨地图恢复需明确破坏当前世界的边界与失败处理，不能暗中load_world。
- 对象纹理版本已验证Audi A2车身和walker.pedestrian.0001裤装槽14；其他型号、任意原厂车色属性、逐笔编辑历史未覆盖。行人需附加studio-pedestrian-slot-material引擎补丁，不能只更新Python。
- 任意外部Unreal写入、外部CLI或preset进程并不自动受全部会话互斥和崩溃恢复保护。
- 源资产导入失败保留已创建资产与报告，不是跨引擎/文件系统原子回滚。
- 预测点时间间隔尚未验证，因此不提供伪造ADE/FDE；BEV_RGB不是语义真值。
- 跨机运行、目标机Python/CUDA/引擎安装验收未完成，场景ZIP不包含源码、权重、数据集或编译资产。
- GitHub推送尚未完成；当前只有本地提交，远程推送范围仍待用户确认。不要重试已被拒绝的推送，也不要声明已同步GitHub。

用户要求按原计划持续开发，只有确实需要用户选择/外部条件且无法继续推进时才停止。不要因为到达一项提交或测试阶段就结束整个任务。

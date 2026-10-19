# 原版模型工作进程异常退出与录制恢复

最新状态：2026-09-15 ThinkTwice 重跑通过，见文末。下文早期“ThinkTwice未通过”为保留的历史失败过程，不是最新结论。

目标属于 S1/S4/S5：模型异常不能被报告为正常完成；只清理纳管资源；中断数据不能冒充完整录制。此验收不是 CARLA 服务端崩溃测试。

## 可复现入口

`tools/regression_worker_crash_recovery.py --original-model driveadapter|thinktwice` 通过既有会话创建4秒场景，至少录制40帧后，仅对该工作进程注入 SIGKILL。

注入前检查执行ID、PID/启动时间、命令全量匹配、模型、场景路径和哈希、录制执行归属及recording状态；检查不一致必须拒绝。注入后要求 failed/-9/process_exit，result_assessed=false；资源日志recovered，同一episode、异步、零传感器，原纳管actor全部消失，启动预检重新ready。源manifest保留recording，必须显式创建恢复副本。

代码增加8项身份不匹配拒绝用例，1087项项目Python测试通过（2026-09-15，6.71秒）。断言型验收拒绝Python -O。常规取消和强杀是不同验收路径。

## DriveAdapter 已验证（2026-09-15）

执行 `5add8a0444c14c3080d4430341fc586a`，故障后 failed/-9，process_exit，未评估驾驶结果。资源恢复后5秒21次观察，同episode496799693756370448、异步零传感器、帧177633→179760。源录制 `capture-20260915T181714-8e40f6ef` 保留40帧和recording状态。

- [原生故障报告](../runs/validation/worker-crash-recovery-9bd3ea25110f4144a3c8693100684ff0.json)
- [浏览器恢复与回放](../runs/validation/browser-models-801af2f1-13b4-476f-b7e0-2111c11cacda/report.json)
- [恢复请求收据](../runs/validation/browser-models-801af2f1-13b4-476f-b7e0-2111c11cacda/capture-recovery-report.json)

界面显式确认生成 `recovered-def077d5eb7148d2bc56c6a27b9abae8`，原目录未修改，副本原始数据及31预热/9有效空间预测通过。打开副本后四原始相机、大图、六辅助RGB/深度、预测叠加通过；人工查看恢复完成截图。提示恢复子集不是完整录制，没有伪造未来时间指标。

![恢复完成](../runs/validation/browser-models-801af2f1-13b4-476f-b7e0-2111c11cacda/capture-recovery-complete.png)

## 边界

ThinkTwice 同路径尚未通过：执行 `7bf7e17891914f91ab3040b027c5768c` 的观察脚本以143退出，原报告 `worker-crash-recovery-aec536eb9c2d4ec393b59ff5404e1262.json` 仍为waiting，不是成功证据。宿主机随后核对模型工作进程仍活着、第46步推理；没有重新创建任务，按精确执行ID正常停止，最终stopped/130、result_assessed=false。这不算ThinkTwice强杀恢复验收。143与SIGTERM终止一致，但信号来源尚未确定，不能归因CARLA崩溃。

修复验收脚本缺口：为SIGTERM安装异常展开处理，使已有BaseException清理路径尝试停止同一执行，最终恢复原处理器；新增退出码143单测，9项身份/终止专项通过。该修复还未完成真实信号注入验收，不保证SIGKILL观察脚本时也能清理。下一步先验收观察器中断保护，再重跑ThinkTwice工作进程故障测试。

本测试不证明磁盘写入中任意指令点被打断、服务端崩溃、全部地图、长路线或跨机器恢复。保留源故障录制与恢复副本供回归，没有删除历史证据。原版模型公开入口仍禁用。

最终收尾：1088项全量Python测试通过（7.05秒）、diff检查通过。ThinkTwice正常停止后另观察5秒21次，同episode、帧226592→228901、异步零传感器；普通桥接恢复（当次PID29484），两模型临时开关关闭。没有把观察器143退出或尚未完成的ThinkTwice强杀验收记为通过。

### 后续：真实操作系统信号回归

新增两项真实子进程SIGTERM测试，执行验收脚本main()而非只调用信号处理函数：等待处理器已安装和观察进入请求后，由父进程发SIGTERM；断言子进程143退出、失败收据落盘。会话仍为owned时必须发送精确执行ID停止请求；会话已变为new-owner时绝不发送停止。父进程有明确等待上限，并只清理自己创建的测试子进程。

11项故障身份/观察器专项通过。这里HTTP和CARLA是测试替身，不执行模型、不消耗采集空间；它证明真实SIGTERM会进入main清理分支及跨执行保护，不证明远端停止已经成功、网络异常时恢复或SIGKILL观察器后清理。ThinkTwice工作进程强杀与真实恢复仍待重跑，阶段状态不变。

## ThinkTwice 重跑通过（2026-09-15）

执行 `e85e1fa5410c45b5b02f2026703e4186` 使用已加入观察器中断保护的脚本，达到40帧后强杀核对过身份的工作进程。报告 failed/-9/process_exit、result_assessed=false；资源日志 recovered，原纳管actor消失，预检ready。同episode496799693756370448、Town04，5秒21次观察异步零传感器，帧290590→292735。

源录制 `capture-20260915T182516-548682b0` 保留40帧、recording状态，未冒充正常完成。浏览器显式确认创建 `recovered-25d6dea7e8c54864982dd4c1d700537c`；原数据哈希检查确认未改动，恢复副本原始数据通过，预测专项31预热/9有效输出通过。副本四原始模型相机、1600像素前图、六辅助RGB/深度和空间预测回放通过，人工查看预测截图；历史36点、未来4点，没有伪造录制后的未来。

- [原生故障报告](../runs/validation/worker-crash-recovery-f4e6c702b0b145078ce0cc1200a8e552.json)
- [浏览器恢复回放报告](../runs/validation/browser-models-5b31027a-448b-41c5-ad03-84e6123263bd/report.json)
- [恢复收据](../runs/validation/browser-models-5b31027a-448b-41c5-ad03-84e6123263bd/capture-recovery-report.json)

![恢复副本预测回放](../runs/validation/browser-models-5b31027a-448b-41c5-ad03-84e6123263bd/prediction-overlay.png)

本轮无新程序改动，沿用上轮1090项测试基线，diff检查通过。完成后关闭临时ThinkTwice开关、保留CARLA和前端。两模型现有工作进程强杀及录制恢复代表案例均通过；完整换图、服务端故障和长时间驾驶矩阵仍未完成，公开入口不放行，八阶段不标记整体完成。

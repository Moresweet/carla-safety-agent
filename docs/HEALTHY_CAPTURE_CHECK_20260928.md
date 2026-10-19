# 健康重连与真实采集回归（2026-09-28）

## 结论与范围

在加入独立进程健康探测后，启动单个可视化 CARLA Town04，未重启桥接；桥接从离线预检失败恢复为 `ready=true`，地图为 `Carla/Maps/Town04`、异步模式。真实独立规则驾驶采集及退出清理通过。没有运行端到端模型，不能将本次结果外推到所有模型、换图或运行中引擎崩溃。

## 本次验收结果

| 检查 | 结果 |
|---|---|
| 实际执行 | `6e2a6bf3aeba42b68b056f69f212210f`，120 仿真帧 |
| 新录制 | `capture-20260928T211522-90648ed9`，40 个同步样本 |
| 生命周期 | 重复启动拒绝；正常完成；无采集/清理错误 |
| 原始数据 | `sensor_input.npz` RGB、米制深度、XYZI 点云、BEV 校验通过 |
| 外参 | 14/14 路通过 |
| 时间与地图 | 每 3 帧保存，无异常间隔；录制地图归档及哈希校验通过 |
| 实际运动 | 位移 36.099 米 |
| 退出观察 | 5 秒、21 次检查，异步模式、0 传感器、无残留采集车辆 |
| 浏览器 | 新录制六路 RGB、六路深度均解码成功；截图人工查看，无卡片重叠 |

主收据：`runs/validation/sensor-rig-b45df920ee894a1aa2ff3f01fe062fb3.json`。

浏览器回放：`runs/validation/browser-models-58d123b2-5905-4def-9657-492d68e9436b/`。

页面导航截图：`runs/validation/browser-models-97f2284a-4aab-4dd0-af72-55df6dad938a/`。导航成功不代表页面全部功能已验收。

![本次录制六视角 RGB 与 BEV](/home/moresweet/Documents/ChatGPT/SafeAgent/carla-safety-agent/runs/validation/browser-models-58d123b2-5905-4def-9657-492d68e9436b/six-rgb.png)

![本次录制六视角深度与 BEV](/home/moresweet/Documents/ChatGPT/SafeAgent/carla-safety-agent/runs/validation/browser-models-58d123b2-5905-4def-9657-492d68e9436b/six-depth.png)

## 明确保留的问题

- 客户端报告版本 `f06817e84`、引擎 `f06817e84-dirty`，输出版本可能不兼容警告。本次数据及生命周期验证通过，不代表所有 API 兼容性已确认。
- 引擎启动日志含运行模式下部分实例分割材质只能粗粒度显示的警告；本次没有验收实例分割。
- Low 画质下近处墙面存在模糊，RGB 图像成功显示不等于纹理视觉质量验收通过。
- 顶视 RGB 不等于语义 BEV；独立采集没有模型预测，页面明确显示无预测，不补造轨迹。
- 正常连接恢复已验证；探测成功之后服务突然失效、编辑 RPC 崩溃和长时间压力仍未完成。
- 新录制保留，未删除任何旧数据。CARLA、桥接及前端保持运行供查看；本次引擎 PID 为 56361，仅为本次观测，不可在后续未核验时据此终止进程。

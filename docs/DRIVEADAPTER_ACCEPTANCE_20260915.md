# DriveAdapter 新预测契约实机验收（2026-09-15）

本轮推进 S1/S4/S5；八阶段整体仍未完成。启动前宿主机确认 CARLA/桥接均无进程，使用现有恢复脚本启动可视化 Town04；没有把旧会话记录当作仍在运行的依据。

## 通过项

- 原生执行 `58e2134a77a24cc8a79dd98b41f7a0ee`：4 秒仿真、80 步，completed/0，结果身份与场景检查通过。
- 新录制 `capture-20260915T180324-f1610aad`：80 帧 saved，基础原始数据校验与 DriveAdapter 预测专项均通过；31 帧预热，49 帧有效空间预测。
- 完整录制验收脚本补充真实退出后健康门槛，不再只凭进程退出和文件完整判通过。实际观察 5 秒/21 次，episode 496799693756370448，帧 13359→15337，Town04、异步、零传感器。
- 浏览器回放第 41 个样本，模型四路原始图像与 1600 像素正前大图、辅助六 RGB/六深度、四点预测叠加、六相机点云深度交叉检查显示通过。人工查看四相机、六深度和预测截图；页面明确不计算 ADE/FDE。
- 1067 项项目 Python 测试通过（6.88 秒），其中采集验收和世界健康专项 16 项通过；git diff 检查通过。本轮未修改产品前端代码，未重新运行生产构建。

## 证据及修正

[原生验收报告](../runs/validation/driveadapter-native-38054bc740294beeb08b1a50955f8d4d.json)

[最终浏览器报告](../runs/validation/browser-models-1e1d9f5a-2442-4c4b-b088-287efc6d8e12/report.json)

第一次浏览器验收在辅助六视角计数失败：通用 CSS 选择器同时选中了模型四路和辅助六路，共十路。已修正测试排除模型四视角区域，并修正截图滚动目标，同一数据集复测通过。不是六幅图丢失，也没有降低“六路全部加载”的门槛。失败证据保留在 `runs/validation/browser-models-7ab8dffa-e7ac-40b0-b8b0-6cf36b9acbaa`。

![模型原始四视角](../runs/validation/browser-models-1e1d9f5a-2442-4c4b-b088-287efc6d8e12/model-four-views.png)

![辅助六视角深度](../runs/validation/browser-models-1e1d9f5a-2442-4c4b-b088-287efc6d8e12/six-depth.png)

![预测与录制轨迹空间对照](../runs/validation/browser-models-1e1d9f5a-2442-4c4b-b088-287efc6d8e12/prediction-overlay.png)

## 未完成与运行状态

未验收采集中取消、完整故障/换图矩阵、长路线驾驶质量。图像仍有偏亮及草地路面外观问题，截图通过不代表视觉质量已解决。空间预测时间间隔未验证，不提供伪造的时间误差指标。

验收结束恢复普通桥接（当次 PID 16767），关闭临时 DriveAdapter 开关；公开入口仍不放行。CARLA 与前端 localhost:3000 保持运行。没有新增数据清理，没有提交或推送 GitHub。

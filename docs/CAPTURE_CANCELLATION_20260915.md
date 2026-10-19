# 两原版模型采集中取消验收（2026-09-15）

本轮推进 S1/S4/S5，不代表完整故障矩阵或八阶段完成。

新增 `regression_thinktwice_native.py --model thinktwice|driveadapter --cancel-with-capture`：在至少40步完成推理后按本执行ID停止。与不录制取消互斥；必须确认 stopped/130、result_assessed=false、benchmark_failed=false、无失败分类。只接受单个40至79帧的已收尾数据集，原始数据和预测都必须有效；完整80帧不能冒充中途取消，未收尾/容量限制/写入错误均拒绝。退出后连续5秒只读检查异步世界、零传感器及帧推进。

## 实机结果

| 模型 | 执行 | 数据 | 结果 |
|---|---|---|---|
| DriveAdapter | e59d2d715b0e4eb59d2fab5d9f55d65f | capture-20260915T181009-742e6af8 | 第40步请求停止，40帧 saved，31预热/9有效空间预测，全部校验通过 |
| ThinkTwice | 02ed42c09aa242f89d9f4f6d7609da26 | capture-20260915T181234-755a59be | 第40步请求停止，40帧 saved，31预热/9有效空间预测，全部校验通过 |

二者均 stopped/130，不评估为完整驾驶结果、无错误分类。相同 Town04 episode 496799693756370448；各21次/5秒观察异步零传感器，分别帧78305→80397、101583→103733。

- [DriveAdapter 原生报告](../runs/validation/driveadapter-native-bf6b6321b4e8495f928e464140e20aed.json)
- [ThinkTwice 原生报告](../runs/validation/thinktwice-native-b0773745b7f949d187040a5ef8df3f92.json)

## 停止后回放

两录制均浏览器选择第36个样本，验证四原始模型相机/1600像素大图、辅助六RGB与六深度、预测空间叠加；最终报告通过。人工查看两者预测截图，可见历史36点、未来4点和四个模型规划点，没有补造录制结束后的未来，也未计算ADE/FDE。

- [DriveAdapter 浏览器证据](../runs/validation/browser-models-193e576c-c776-49c9-bad9-bf41ceace500/report.json)
- [ThinkTwice 浏览器证据](../runs/validation/browser-models-6e8b7c7c-6031-43be-915c-d1de9fddaf2c/report.json)

![DriveAdapter 停止后轨迹](../runs/validation/browser-models-193e576c-c776-49c9-bad9-bf41ceace500/prediction-overlay.png)

![ThinkTwice 停止后轨迹](../runs/validation/browser-models-6e8b7c7c-6031-43be-915c-d1de9fddaf2c/prediction-overlay.png)

## 测试与边界

新增部分录制边界与错误取消状态用例。第一次全量测试有一个旧夹具缺少新 outcome 字段而失败；补齐夹具并增加“取消被误评估/取消带执行错误”的拒绝用例后，25项专项、1079项全量Python测试通过（6.73秒），diff检查通过。

正常中途停止不等于强杀、磁盘耗尽、CARLA崩溃或任意地图恢复。两模型完整故障/换图/长距离驾驶矩阵仍未验收；公开入口继续禁用。验收后恢复普通桥接，关闭临时开关；CARLA/前端保持运行，没有额外清理历史数据或推送GitHub。

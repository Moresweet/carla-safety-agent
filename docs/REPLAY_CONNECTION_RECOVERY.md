# 回放与切图连接恢复（2026-09-14）

本轮已实现，不代表长期无崩溃保证：

- 回放索引、帧元数据和图像最多尝试三次；超时/短暂断连有界重试，持续失败停止并提供手动恢复。
- 切换数据集取消旧请求，播放等待对应帧元数据；失败暂停播放，不将旧帧当作新结果。
- 图像手动恢复使用独立请求标识，避免失败缓存导致“点击重试但没有重新请求”。
- 场景轮询串行、可取消、有超时。切图期间 HTTP 503 保留上次视图并明确提示连接异常，不覆盖有效世界数据。
- 桥接先读取场景再写 HTTP 状态，旧世界/RPC 不可用返回结构化 503；客户端断开不重复读取世界。写操作不自动重试。

## 浏览器证据

`runs/validation/browser-models-75864c56-5d8a-4577-9aa6-676a369e8e47`：短暂错误恢复、三次耗尽停止、手动恢复、场景 503 后恢复全部通过。使用真实录制数据，断网通过浏览器注入，不启动模型。

![图像读取失败明确停止](../runs/validation/browser-models-75864c56-5d8a-4577-9aa6-676a369e8e47/images-retry-exhausted.png)

![手动恢复图像](../runs/validation/browser-models-75864c56-5d8a-4577-9aa6-676a369e8e47/images-manual-recovered.png)

![场景不可用保留视图](../runs/validation/browser-models-75864c56-5d8a-4577-9aa6-676a369e8e47/scene-read-unavailable.png)

## 原生回归

`runs/validation/map-transition-d015f5e569db4b7f958d75f886da67cb.json`：VAD Town05、Town04 两次真实闭环各 20 帧通过；同步 RGB、深度、XYZI、BEV 校验通过，17/18 传感器外参验证，缺少的历史外参不算通过。退出后异步、零传感器，分别观察 5 秒持续推进。当前 episode 为 4926267799737637651；本次回归未崩溃，不能据此断言历史 UE Signal 11 的唯一原因是切图。

949 项项目 Python 测试和 TypeScript 检查通过。根目录无范围 pytest 会误采集隔离第三方库测试，正确命令为 `PYTHONPATH=src python3 -m pytest tests -q`。

最后增量再次验证：实时状态轮询改为串行超时请求后，生产构建通过；浏览器 `browser-models-0e3dffd2-8fc9-4a43-8b68-b72ffc102142` 再次通过上述故障注入与恢复，恢复后六视角截图已人工查看。该次不包含额外的六视角深度切换步骤，不替代前次对应证据。

后续：长时间断连压力、采集实时状态故障注入、存储容量管理。旧 HTML 验收报告保持冻结，本文件记录后续增量。

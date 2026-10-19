# 原版模型跨地图回归（2026-09-15）

本轮将既有 `regression_map_transition.py` 扩展到 ThinkTwice/DriveAdapter。原五模型仍沿既有时长，新模型每图4秒/80帧，以越过31帧预热并验证真实预测。开始前要求空闲、Town04、无车辆/行人及未修改编辑场景；保存快照。两新模型在首次服务请求前要求10GiB可用空间覆盖两次采集预算，不能先切图再发现可预见的容量不足；两项准入拒绝测试通过。

## ThinkTwice 往返通过

| 阶段 | 执行 | 数据与结果 |
|---|---|---|
| Town04 → Town05 | d2f9708e29654f96bf5acd251d595e85 | capture-20260915T183237-1037985b；80帧saved，31预热/49预测，完整数据通过 |
| Town05 → Town04 | 03964088093946648af1b41f47fe99db | capture-20260915T183736-10c0f89d；80帧saved，31预热/49预测，完整数据通过 |

两执行均completed/0。episode由496799693756370448变为3370953518767652327，再变为14943196763826352962。两次退出各5秒21次检查异步零传感器、世界帧递增；每图预检重新ready。最后恢复保存的场景9ac8edbc95fb4c3fa57657c595c4d256，报告original_editor_restored=true（恢复接口成功，不是本次另做所有材质槽逐像素校验）。

[原生往返报告](../runs/validation/map-transition-93c9d3781211416bac0c4e798b87dd9c.json)

两图分别在第36个录制样本验证原始四相机/1600像素前图、六辅助RGB/深度、空间预测叠加。浏览器报告通过，人工查看Town05四相机和返回Town04预测截图。可视化在各自录制仍进行时读取已落盘样本，最终完整数据校验由原生脚本在任务终止后完成。

- [Town05 浏览器报告](../runs/validation/browser-models-15d5be6f-3707-40b9-b07a-d69c3b0e1856/report.json)
- [Town04 浏览器报告](../runs/validation/browser-models-c7fea761-8570-4203-9cca-fc257e926ee5/report.json)

![Town05模型四相机](../runs/validation/browser-models-15d5be6f-3707-40b9-b07a-d69c3b0e1856/model-four-views.png)

![返回Town04后的预测](../runs/validation/browser-models-c7fea761-8570-4203-9cca-fc257e926ee5/prediction-overlay.png)

1098项Python测试通过（6.92秒），diff检查通过。结束后恢复普通桥接，关闭ThinkTwice内部开关；CARLA/前端保留。没有删除数据，没有推送GitHub。

## 未完成

DriveAdapter同类往返尚未执行。两张地图短程通过不是任意地图、长路线驾驶质量、服务端崩溃或所有失败组合的证明；画面偏亮等视觉问题仍存在，空间预测时间契约未验证，不计算ADE/FDE。S1及八阶段整体保持进行中，公开新模型入口仍禁用。
# 2026-09-15 DriveAdapter 双向换图最新验收

## 两地图新录制可视化验收

Town05与返回Town04均已浏览器验证原始四相机加载及1600px前视放大、显式选择第41个样本（索引40）、空间预测/真实轨迹叠加、六辅助RGB与六深度加载。两张预测截图已人工查看；只表达空间对照，仍不计算ADE/FDE。

初次测试默认首帧，因31帧预热期无预测而断言失败；未改变模型逻辑或伪造预测。测试工具新增--sample-index并校验实际帧下载链接已切换，预热后重跑通过。失败证据保留在browser-models-8012b7a6-39b2-4b84-84cc-bb76ea773251及browser-models-a765473c-029b-474d-a646-0ee97acc7b79。

![Town05空间预测](../runs/validation/browser-models-567612cf-d297-47c8-8f39-ddaaa0664a3c/prediction-overlay.png)

![返回Town04空间预测](../runs/validation/browser-models-e78a89b3-bccb-490e-878d-fad333073a43/prediction-overlay.png)

完整网页报告在上述两个截图目录的report.json；本次无新仿真录制，替代下文“专门网页截图尚待验证”的历史状态。

在清理两份被替代旧录制后，10GiB磁盘准入通过。原版DriveAdapter受控运行Town04→Town05→Town04，两地图各80帧完整原始输入采集通过、31帧预热/49帧空间预测验证通过。两轮会话completed且退出码0，退出后5秒21次观察均异步、0传感器；原工作台快照恢复成功。

- Town05：capture-20260915T203947-06eab94d，执行953dfcddf836497186a3bfa610f786b6，episode4598729839077222600。
- 返回Town04：capture-20260915T204506-23771c1a，执行e6090eb541a0404ba3c15a74912bc703，episode8939530053782256487。
- 收据：runs/validation/map-transition-f89370b55c6f49e08d1b87fc26b6c4b0.json。
- 两录制已显式标记保留，保留清单revision7共5项；临时实验开关已移除，桥接171087，公开入口仍不开放。
- 全量Python1262项通过（46.25秒）。新录制后磁盘余量约3.5GiB，不宜继续启动大录制。

此结果更新下方DriveAdapter换图尚未开始的历史状态，不代表长路线驾驶质量、任意地图或CARLA进程崩溃矩阵通过。新换图录制的专门网页回放截图尚待验证。

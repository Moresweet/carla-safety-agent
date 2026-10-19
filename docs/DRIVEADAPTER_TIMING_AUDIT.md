# DriveAdapter 预测时间来源核对

状态：源码候选证据，尚未启用timing_verified或ADE/FDE。2026-09-15只读检查本地原版源码，无新增录制。

## 当前保存分支与生成时刻（后续核对）

本地原版 `leaderboard/team_code/driveadapter_agent.py:500` 明确将forward_inference返回的pred['pred_wp']传入model.control_pid；适配器没有覆盖该run_step。`open_loop_training/code/encoder_decoder_framework.py:377–380` 在轴交换之前复制saved_waypoints，438–441行将四个原点写为wp_1…wp_4。因此当前捕获的是训练pred_wp分支的原始四点，而不是PID瞄准点或最终转向控制量。

项目PlanningObservation在原control_pid返回时保留该metadata和生成帧/时间/自车矩阵，原控制输出不变；prediction_trajectory.raw_points对原版模型做forward_right→right_forward轴交换。原版最终control.steer主要来自另一process_action分支，不能把预测点称为实际执行路径。

对新返回Town04录制capture-20260915T204506-23771c1a逐帧只读检查：49帧包含planning_anchor，共49个不同生成帧，录制时间减生成时间均为0秒。本数据集没有观察到复用延迟；这不证明任意运行永不复用，也不代替通用指标中的生成时间处理。

已减少待核对项：当前输出分支来源明确、此录制生成时间可用。仍需训练数据/权重时间溯源、参考点到真值的精确对应与未来时间匹配策略，故保持timing_verified=false，不改写历史录制。

## 已确认的本地源码链

- `open_loop_training/configs/driveadapter.py:43`：pred_len=4。
- `open_loop_training/code/datasets/carla_dataset.py:138`：未来标签依次读取route_index+1…+4的measurements，使用未来位置产生waypoints。
- `open_loop_training/code/model_code/dense_heads/driver_adapter_head.py:397`：pred_wp形状为pred_len×2；438/507行使用batch waypoints计算训练损失。
- `leaderboard/team_code/roach_ap_agent_data_collection.py:450`：每次调用step递增；501行每10步保存一次，572行以step//10-2为记录编号。奇数步控制复用不改变该编号规律。
- `leaderboard/leaderboard/leaderboard_evaluator.py:106,264`：20Hz、fixed_delta_seconds=1/frame_rate。

由这条采集—训练源码链推导候选未来时间为0.5、1.0、1.5、2.0秒。它不是当前50ms录制间隔，也不是控制器调用间隔。

## 尚不能直接启用指标的原因

需核对权重对应的数据生成版本/设置、当前适配器保存的空间点是否正是该pred_wp分支、控制器变换及参考原点、复用预测的生成时刻。最终还需按预测生成时刻匹配已录制未来真值，明确时间插值/缺失/末尾不足处理。不凭上述推导给历史录制回写已验证时间字段。

## 源文件SHA256

- carla_dataset.py：b6473fe9f63ec4fd8f13869c1afeb7b1abb46f6cf494e5e554b47ee0aa933986
- roach_ap_agent_data_collection.py：07cc2dad08eb8ceb9d117e6e5aed306918eebcbcc7b10c845ab7a75c6fd1e47b
- leaderboard_evaluator.py：8c0c2ff7d2717984eeaaf31e83fcbaf0b456d43222c7465b79335d002031671d

路径均相对 `.runtime/external-models/DriveAdapter`。这些校验和用于定位本次证据，不代表官方发布版本或权重训练溯源认证。
# 回放参考点限制补充

## 2026-09-28 连续回放测试准备与环境变化

补充响应frame身份检查，切数据集时清空轨迹就绪标记；浏览器脚本新增 --trajectory-backpressure，注入下一轨迹请求等待并验证时间轴不前进，随后注入读取失败验证暂停。TypeScript通过。

实际浏览器尝试未到业务测试：`browser-models-5c4545e9-87b6-4880-8466-368b5808b40c` 在查找Generate Scene失败。只读复核localhost:3000拒绝连接，pgrep无前端/桥接进程，先前PID已失效；不能称背压浏览器测试通过。需恢复服务后继续。

## 连续播放的轨迹读取背压

真实v2录制索引40、41、42、40逐次隔离投影耗时约0.208、0.233、0.192、0.200秒。原回放定时器可按0.05秒间隔切换，独立轨迹请求可能被连续取消，不能保证每帧有轨迹显示。

前端现等待同run_id、同frame的轨迹读取成功后才安排下一帧；轨迹读取20秒超时或失败会暂停，切帧/切数据集取消的旧请求不回写。明确提示实际速度可能低于所选倍速，不以跳帧掩盖处理耗时。TypeScript通过；该背压行为的浏览器连续播放与故障注入测试尚待完成。不是提升到实时20FPS，也不代表图像资源已全部解码同步。

## 最新完整录制：v2参数、地图归档与网页投影

真实执行 `bb0514da7c2248258f3e36e7b5335007`，录制 `capture-20260915T220648-e208b12c`：80帧saved、无错误、22/23外参通过，31预热49预测。49帧严格v2参数/归档地图逐点投影复验通过，转换后导航原点最大偏差0.0905598885m。最终复验收据 `runs/validation/driveadapter-projection-v2-final-20260915.json`。

首次总报告 `driveadapter-native-416583c2892f411ba7ffc2a4979511cb.json` 保持ok=false：已运行脚本将校验PYTHONPATH覆盖为src，原生投影子进程失败。已修正脚本保留调用环境；未重复录制、未篡改失败报告。原报告证明执行正常、原始数据通过以及退出后5秒21次异步零传感器；修正环境后对同一完整录制的独立严格复验通过。不能称首次一键验收通过。

浏览器真实选择索引40显示4个逐点投影预测点和0.041m导航原点偏差，人工查看截图：`runs/validation/browser-models-3eda405f-bd05-4d07-8613-39450ab0c32d/prediction-overlay.png`。不显示旧2.4m数值差，不计算ADE/FDE。新录制已保留revision15。临时实验开关关闭，桥接PID255011。全量1306项测试、前端生产构建通过（既有Unknown路由分类警告保留）。

仍缺：可靠预测时间/权重训练版本契约、误差指标、跨地图离线回放及吞吐压力测试；本次不代表S5整体完成。

## 完整DriveAdapter验收不再只检查旧空间契约

标准 `regression_thinktwice_native.py --model driveadapter` 现自动要求 `--require-map-projection`：所有预测帧必须具备v2运行时导航参数、通过录制归档地图的隔离进程逐点转换，并记录地图哈希、转换帧数和投影后原点最大偏差。缺失任一项使prediction_valid为false，完整80帧验收不得通过。ThinkTwice原验收不受影响。

33项相关验收/隔离/转换测试通过。对真实旧v1录制执行两种校验：普通空间校验仍通过，严格地图/v2校验明确拒绝（Runtime navigation parameters were not recorded）。没有为通过新验收回填旧数据；严格成功路径仍待真实新模型录制。

## 导航换算参数随新观测保存

新DriveAdapter导航观测升级v2，保存实际route_planner.mean/scale与明确坐标标签 original_route_planner_xy_not_carla_world。保留world_xy_m字段名仅为历史兼容，不宣称其数值属于CARLA世界。回放v2按记录参数逆算，校验有限数字、原点范围、正比例；v1仍明确采用审核过的历史固定常量并返回参数来源，不重写旧数据。

67项包装器/投影/导航/预测测试通过，包括运行时非默认原点比例和参数拷贝隔离。v2尚未实机录制，不能将此前v1实测替代v2验收；完整模型带地图归档链路仍待完成。

## 新地图归档真实采集验收

桥接以原环境加载到PID234517，未开启实验模型。标准独立autopilot采集 `capture-20260915T215724-38c1288b` 完成120仿真帧/40录制样本、移动36.099m，原始数据及14/14外参通过，地图OpenDRIVE归档哈希4dddd1560ab7812b0e89cd4a523d8b6f2b93947eafb496d9eeb83cc772116c85通过。退出后5秒21次检查异步零传感器。报告 `runs/validation/sensor-rig-9e4dba0ec09642408713c327bf542667.json`。

浏览器六RGB/六深度加载与截图通过，目录 `runs/validation/browser-models-719acacd-a2ee-47d2-904a-2aa69bc03e07`。此录制没有模型，不替代DriveAdapter带投影归档的完整验收。另直接调用真实隔离子进程对另存Town04+历史预测帧得到有效4点结果，无仿真连接；仍不回填旧录制。

本轮44项地图/离线隔离/回放/恢复/片段测试通过。磁盘空间不足以立即启动另一份完整80帧原版录制，完整模型链路仍需后续验收。

## 网页区分归档地图轨迹与规则参照

RecordedTrajectory 现优先显示经校验的 map_projected 点：要求生成帧一致、地图SHA256格式有效、4个有限三维点、未启用时间/误差指标且导航距离有效。显示逐点投影来源、投影后导航原点偏差与高度限制。缺失或失败仍显示原规则参照，但明确说明未完成地图投影，不伪造成功；已转换时不继续展示未统一坐标的2.4m数值差。

前端选择逻辑测试与TypeScript通过；浏览器真实新归档录制验收尚待完成，未将本次UI代码实现视为已实测交付。

## 离线投影接入回放接口（界面切换待完成）

回放接口对有效DriveAdapter预测增加 map_projected：只从录制map_projection加载，缺失归档不启动子进程，不取当前地图。原生carla.Map解析与转换在独立一次性子进程中执行，15秒超时、单任务门禁、请求/结果大小限制，退出异常/非法响应返回unavailable；已有真值与规则参照轨迹保留。该结果尚未切换到网页主轨迹，服务尚未加载本轮代码。

新增失败隔离测试覆盖模拟signal11、超时、非法JSON、错误地图哈希和非法点数。没有把模拟崩溃当作真实CARLA服务崩溃验收；实际新录制端到端仍待完成。

## 逐点地图转换数值层

新增 projected_prediction：先通过已有预测/导航契约门禁，再按生成时航向将4个预测点转回原版导航坐标，逐点还原经纬度、调用归档地图投影，最后转换到当前回放自车坐标。原点也独立投影，不使用固定偏移。高度暂取生成时自车高度，不伪造道路高程；时间契约与ADE/FDE仍未启用。

47项转换/预测测试通过，含各向异性投影（证明每点转换而非只移动原点）、航向旋转、当前位姿平移、非法结果与缺失导航拒绝。以独立保存Town04的 `map-projection-rncaiiz2` 离线重建Map，对最新真实录制49预测帧执行成功，每帧4点、转换后导航偏差最大0.0905598885m。没有CARLA Client连接；但地图为另存诊断归档，不冒充该历史录制原生携带的地图证据。数值层尚未接入HTTP/UI自动选择；完整新录制仍需验收。

## 投影归档的派生数据迁移修正

新录制 files.map_projection 指向内容寻址OpenDRIVE文件；原始校验器要求它与map_projection.path一致，防止manifest有声明而迁移遗漏文件。事件片段白名单新增此类型，仅在路径/哈希校验后复制；恢复副本沿文件清单保留原归档。新增片段ZIP与恢复副本字节一致性用例，连同已有用例36 passed。这里的测试原始数组为fixture，不能替代真实新录制恢复验收。离线轨迹转换仍未接入，旧录制仍不回填当前地图。

## 录制地图归档实现及离线投影验证

SensorCapture 新录制保存当时 world Map 的 OpenDRIVE 原文，文件名包含 SHA256；manifest 记录 map_projection、地图名、geoReference 和来源。缺失投影明确 unavailable，不使用当前地图默认值。读取验证路径、符号链接、32MiB上限、XML实体声明及哈希；原始数据校验器检查可用归档与地图身份。旧录制不回填。

60项地图归档/采集测试通过。真实当前Town04导出至独立 `runs/validation/map-projection-rncaiiz2`，再仅用保存原文创建离线 `carla.Map`，4个位置的正逆投影往返误差均0m。此项不调用load_world/tick，不修改旧录制。尚未加载本轮采集更新，也未完成新录制从采集到回放的完整验收；轨迹点转换仍待接入。

## 地图逆投影验证及诊断语义修正

本地 CARLA Python Map 暴露 `geolocation_to_transform`。对同49帧：先将原版导航 XY 按原始 scale 还原经纬度，再调用当前Town04逆投影。原始GPS往返真实XY误差最大0m；转换后的平滑导航位置与真值误差范围0.0012763683–0.0905598885m。没有修改原模型输入或运行结果。

因此此前2.38–2.47m应明确称为“未统一地图投影的坐标数值差”，不能称实际物理定位误差。API新增 measurement_kind 标识；UI同步修正措辞，保留旧录制字段兼容。54项导航/预测测试通过。此次逆投影是依赖当前Town04的只读诊断，尚未接入脱离当前地图的离线回放，不宣称历史坐标修复完成。后续需要归档录制时地图投影及换算参数，并对轨迹点和参考原点一起转换，不能仅平移绿线或固定补偿2.4m。

## 偏差定位：主要来自原版固定经纬度比例，而非 GPS 安装偏移

对最新80帧录制的49个预测帧只读复核：GPS标定为车辆原点、零平移；将保存的生成时CARLA真值位置通过当前Town04的 `transform_to_geolocation` 转换，与保存的原始GPS经纬度逐帧比较，最大绝对差为0度。未调用tick或修改场景。

本地原版 `leaderboard/team_code/planner.py` 使用 mean=[0,0]、scale=[111324.60662786,111319.490945]；`_get_position` 按固定比例转换。Town04 OpenDRIVE georeference 声明 `+proj=tmerc +lat_0=0 +lon_0=0 +k=1 ... +datum=WGS84`，本地CARLA `GeoProjection.cpp` 实现对应转换。

同一49帧计算结果：原始GPS按原版固定比例换算后，与真值距离为2.4558978959–2.4711147341m；平滑导航相对该原始固定比例位置的最大距离仅0.0911662844m。因此本次约2.4m偏差主要在平滑前的坐标换算阶段产生，不是传感器安装偏移，也不能主要归因于GPS平滑。这是本Town04短录制的证据，不外推其他地图或长路线。

后续修复必须明确区分：原版模型坐标、地图真实投影坐标、显示参照。不能直接把平滑导航数值当CARLA世界坐标，也不能硬编码减去2.4m。若改变模型的导航预处理，须声明为地图适配变体并重新验收，不能继续宣称与原版行为完全相同。当前未改原版推理或GPS原始输入。

## 最新实机验收：导航参考点偏差确实存在

完整 80 帧 DriveAdapter 原版运行通过，执行 `45adad0e5c1d430f82ba4114a7de2267`，录制 `capture-20260915T213258-365bc848`，报告 `runs/validation/driveadapter-native-f610e7155a074b87be69b692c7c8bec6.json`。80 同步帧、22/23 外参、31 预热/49 预测，saved 无错误；退出后5秒21次检查为异步零传感器。临时实验开关已移除，桥接恢复 PID 215772；新基线保留 revision 13。

额外运行 `tools/validate_thinktwice_prediction.py <dataset> --model driveadapter --require-navigation`：49/49 预测帧的导航观测有效，位置偏差最小2.3795966296m、最大2.4724030068m，航向绝对偏差最大4.1710861e-7rad。不能再将导航位置与真实车辆位置当作精确等价；目前尚未确定偏差来源，不能直接声称是平滑造成，也不据此硬编码补偿。

真实浏览器零基索引40显示偏差2.428m，截图已人工查看：`runs/validation/browser-models-198c6b53-4b5f-4f71-9345-c33739ebff90/prediction-overlay.png`。空间显示仍以真值锚点作规则参照，不启用ADE/FDE。下一步分解 GPS 原始投影、运动补偿与传感器安装位置，以确认准确参考系。

本轮全量Python测试1282 passed，生产构建通过（既有vinext路由Unknown分类警告保留）。本次4秒单地图运行不代表长路线/全崩溃矩阵完成。

## 旧录制真实浏览器兼容验收

空闲门禁通过后，桥接以原环境由 PID 171087 重启到 191967，没有开启实验模型、没有重启 CARLA。浏览器读取 `capture-20260915T204506-23771c1a` 的第 41 个样本（零基索引 40），验证 4 个预测点、ADE/FDE 禁用、DriveAdapter 导航参考点警告以及“没有有效观测，不按零偏差处理”。截图已人工查看，文字及轨迹均显示。

证据：`runs/validation/browser-models-47be439d-c388-4a5d-9191-9a2892bdffe7/prediction-overlay.png` 与同目录 JSON。此项证明旧数据兼容与提示真实显示，不证明新导航字段实机采集成功。磁盘约 3.4 GiB，低于固定 80 帧录制所需 6 GiB，本轮没有启动新录制、没有降低容量门槛或删除历史数据。

新增只读导航参考点诊断：严格检查 schema、来源、模型步号及有限数字，计算保存导航 XY 与预测生成时真实车辆位置的偏差，以及 compass−pi/2 与生成时车辆平面航向的环绕角差。缺失/过期/非法值返回 unavailable，不冒充零偏差；不使用当前回放帧的位置比较旧预测。UI 显示此项独立诊断，不替代 ADE/FDE，不改变空间叠加。54 项导航/预测测试、TypeScript 通过；目前是合成用例验证，未取得新增字段的真实录制及浏览器验收，不能以数值公式存在宣称参考点等价已证实。

后续录制新增观测：DriveAdapter 包装器调用原版 tick 后旁路保存原版平滑 GPS 对应的 world_xy_m 和未经航向处理的 compass_rad；PlanningObservation 仅在模型步号一致的真实 control_pid 调用时深拷贝到生成锚点。复用预测保留旧锚点，不能用当前导航位置覆盖。原版返回对象、推理与控制均不替换；不从旧原始 GPS 伪造已保存的平滑位姿。

相关预测与包装器单测 47 passed。此新增字段尚无实机录制证明；后续需验证序列化、位置偏差与航向转换，再决定精确评估契约。当前不改变空间叠加算法、不启用误差指标。

本地原版 `driveadapter_agent.py` 的 tick 将 GPS 加入缓冲后取均值，`update_gps_buffer` 使用运动模型更新各历史位置。当前规划观测锚点则保存 CARLA 真实车辆位姿。两者未经数值对照，不能视为完全相同的精确评估原点。

回放接口与轨迹面板现明确提示此限制；仅新增回放提示，不改变历史保存的空间契约、不重写原始录制、不启用 ADE/FDE。别的模型不套用本次仅针对 DriveAdapter 的发现。

验证：预测轨迹单测 41 passed，前端 TypeScript 检查通过。尚未重新加载后端或完成该新增提示的浏览器验收；原版推理、控制和已有坐标变换未改动。

# 桥接部署前核查

## 已有零帧失败录制的正式网页校验

在Collect Data选中capture-20260929T141403-17dd8aed（saved_capture_error，0帧），页面正确显示录制锁冲突导致异常结束，播放/前后帧按钮禁用、索引无法验证时序。通过页面按钮发起正式校验，观察running到failed，明确显示“没有已录制样本，无法验证原始数据质量”，并提醒此结果不意味着CARLA崩溃。

展开真实日志显示CSA_CAPTURE_QUALITY的no_samples协议及校验器No recorded samples错误。该流程没有创建恢复副本、触发新录制或修补原数据，仅新增质量报告。覆盖的是零样本失败，不等于损坏位姿在正式HTTP中的故障验收。

![零帧质量检查失败提示](../runs/validation/zero-sample-quality-browser-20260929.png)

## 真实校验器位姿故障注入

`tools/verify_quality_pose_failure.py` 在系统临时目录复制已有两帧录制，先运行真实校验器确认passed，再仅将第149143帧位姿旋转矩阵第一行置零。真实子进程返回failed / invalid_ego_pose / problem_frame=149143；恢复副本元数据后重扫passed。源录制51个文件哈希前后不变，临时副本已自动清除，未留下新增录制。

收据：`runs/validation/quality-pose-failure-20260929.json`。该证据覆盖真实校验器到报告解析的失败协议，不等同于正式HTTP故障注入或前端截图验收；生产源数据从未故意损坏。

## 部署后正式质量重扫通过

通过新增 `tools/verify_deployed_quality.py`，对已有 `capture-20260929T161825-9e1187fd` 从正式HTTP接口发起重扫，观察running到passed。两帧原始RGB/深度/XYZI/BEV一致性及14/14外参校验通过，新报告含problem_frame=null、manifest_freshness=unchanged。验证前后51个录制文件逐文件SHA256完全一致；旧报告在history中完整保留，新报告已落盘，扫描结束datasets/jobs空闲。

收据：`runs/validation/deployed-quality-20260929.json`。这是新部署成功路径的真实接口验证，不是长录制、故障注入或驾驶安全验收；没有新增录制或修改原始传感器数据。

## 正式桥接已重载并验证（2026-09-29 09:51 UTC）

本节取代下文的“尚未部署”历史状态。显式legacy升级模式新增已观察旧版的精确健康响应识别：资产端点、根路径及随机未知路径必须同时返回完全相同的旧健康对象，才执行本地资产证据检查；默认模式不接受此回退。失败/不一致响应不放行。相关138项专项通过。

在真实主机进程空间检查门禁通过，未发现Blender后台或UE4Editor-Cmd导入进程。生产脚本持有准入/import两把锁、再次检查会话/调度/数据任务/地图切换/资产证据后，停止旧桥接1242030，启动1303334。CARLA进程1219324仍在，未执行切图或引擎重启。会话97a33b6384234bbf9802679a038ee0da仍为completed。

部署后实际验证：默认（不带legacy参数）重启检查通过；未知GET返回404/unknown_endpoint；正式资产端点返回asset-restart/1且unresolved为空；旧6项失败仍为needs_attention而非成功。两帧录制质量报告返回新增manifest_freshness=unchanged，证明新质量服务已加载。这里只验证报告读取，尚未重新启动质量扫描或跑完整闭环矩阵。首次升级的旧生成入口没有原子准入保证，不把这次静默窗口成功推广为旧版本全并发安全证明。

## 审查证据读取加固

审查回执在访问文件前校验job/attempt身份；拒绝直接链接的runtime/job、悬空回执链接，避免未找到回执时绕过身份校验。日志/回执使用no-follow、nonblocking打开并检查实际描述符为普通文件，读取上限65536字节，拒绝非对象JSON。新增非对象、路径穿越、链接、FIFO及超大文件测试。相关137项通过，diff检查通过。

以新代码只读复核真实本地资产记录：unresolved仍为空，6项历史启动前拒绝仍由原哈希回执识别，另1项生成失败保持失败；未修改原日志或回执。本轮未部署、未重启服务。此加固不宣称解决所有并发目录替换问题，也不解决旧桥接未知路由返回200的首次升级问题。

## 正式接口检查推翻了404假设

2026-09-29实际运行 `tools/check_bridge_restart.py --legacy-assets` 被拒绝，未重启任何服务。随后GET正式 `/blender/restart-status` 确认返回HTTP 200，内容仅为 `{"ok":true,"service":"carla-surface-bridge"}`。因此旧接口不是已证实的404，而是未知GET路由被通用健康响应掩盖。此前“端点缺失即404”的假设不成立。

已修正代码中的GET兜底：只有根路径返回服务健康，未知路径返回404及 `unknown_endpoint`。新增5项路由测试，桥接/重启/资产联合回归396项通过（11.96秒）。该修改尚未加载到正式进程。没有放宽重启检查去接受任意200或未知结构；首次部署仍需解决旧服务静默维护及身份确认，不能把检查拒绝记为部署成功。

## 首次升级入口实现（尚未执行部署）

新增显式 `--upgrade-legacy-assets` 模式：仅新资产端点返回 HTTP 404 时，才读取同一项目的本地资产日志及绑定哈希的审查回执。普通重启仍要求正式接口；500、超时、未知状态和未解决任务均拒绝。该模式与崩溃/恢复模式互斥，不跳过会话、数据任务、调度器和地图切换检查。

重启脚本同时持有资产准入锁和原生 import.lock，阻止仍持有导入锁的子进程期间重启；两锁在旧桥接退出后、启动新桥接前关闭。专项测试124项通过，覆盖404显式回退、非404拒绝、本地未解决拒绝、真实文件锁下脚本拒绝启动。shell语法检查通过。

这些是代码和隔离测试证据，不是正式部署证据。旧桥接的生成入口不一定参与新准入锁，首次升级仍需受控静默窗口；不能声称此入口已提供所有旧入口的原子维护保护。本轮未停止桥接或CARLA。

本次只读检查，未停止或重载服务。

## 后续实际迁移结果

重新验证session/scheduler、dataset jobs、handoff空闲，并同时持有bridge-restart.lock及import.lock排他锁后，已为下表6条记录写入独立restart-review回执。逐项重新验证历史协调进程已退出、无原生attempt产物、原日志身份与哈希；写入后原日志字节均保持不变。

当前本地restart_status为unresolved=[]，6条仍是needs_attention，仅单列reviewed_prelaunch_rejection，非注册成功。另1条生成失败仍是已退出的失败。没有删除任何日志或资产，没有停止CARLA或桥接。旧桥接的新状态端点缺失问题仍需首次部署兼容处理；这次锁在操作结束后释放，未来重启必须再次检查。

- 当前桥接PID1242030，实际命令python3 tools/livery_bridge.py。
- 正式session/scheduler、datasets/jobs、scenes/handoff经现有restart_guard验证空闲。
- 全部资产日志检查仍有6条旧needs_attention导入；不是6个运行中的导入。
- 每条错误均为Generated asset ID already registered；均有ended_at，无asset_name/destination/request_path/result_path；任务目录按attempt_id匹配只有import-attempt日志本身。
- 进程清单没有实际Blender后台任务或UE4Editor-Cmd导入进程。CARLA编辑器游戏进程不属于要停止的目标。

待审查记录：

| job_id | attempt_id |
|---|---|
| 0f92d5997ced | c7da459243a046a1863dd743faf5b04d |
| 5a42ab78732e | 8b9472537c304b79aff01c3474ccfbea |
| da26fc63cf0b | 58629090edce45019ff4a4e6773f8b16 |
| 888379d80d6b | 27a503a0094e4011afcf277b25929269 |
| 2a3879a4781d | dc3abb116c23454d9956a2b2bf5d12db |
| 849c40ad42ce | 94874d9694344ffd8a91b8d74e2aee61 |

这些组合证据支持“启动前重名拒绝”，但本次不改原日志、不写worker_state、不把失败标成registered。新门禁仍会拒绝这些缺字段记录，旧服务还缺新HTTP状态接口，因此尚不能声称部署完成。

受控迁移须保留原记录、将审查决定绑定原日志哈希及精确任务身份，并重新检查任务/进程/文件锁；首次加载新代码后再验证新接口、位姿质量错误协议、报告新鲜度和运行任务保护。不得用删除旧日志或永久跳过资产门禁替代迁移。当前快照不能作为未来重启时仍空闲的证明。

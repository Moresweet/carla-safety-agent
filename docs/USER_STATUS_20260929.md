# 原开发计划完成情况（2026-09-29）

## 最新磁盘复核

S1/S4 采集失败原因向会话关联开发：sensor-rig 状态文件新增 execution_id，桥接保存独立 worker_execution_id；非零退出时仅读取来源=sensor-rig、执行 ID 精确匹配、大小受限且错误为非空字符串的报告。会话 error 可保留采集原因，outcome 区分 capture_io_error/capture_worker，世界恢复与启动失败仍优先；缺失/旧报告/损坏报告继续通用 process_exit，不猜测。新增身份与坏报告测试并运行 worker/桥接专项；改动尚未部署，真实会话分类需要重跑验证。

S4 恢复候选位置页面已接入：严格校验 staged/published 布尔字段、候选 ID 和 raw_data_verified=false，区分仅暂存、仅目标、两处均有、两处均无四种说明；保持原任务状态，不将目录存在当作数据校验或恢复成功。Node 测试覆盖四组合、非法字段及缺候选身份，TypeScript 与差异检查通过。后端此批候选位置版本尚未重载，网页真实响应展示及中断任务的显式重新审核/完成流程未验收。

S4 恢复候选位置只读核对：status 对合法 recovered UUID 候选返回 staged/published 目录存在性，按服务配置与 request_id 推导位置，不信任持久化任意路径；拒绝链接路径，明确 raw_data_verified=false，不改变原状态/日志。独立进程发布前/后退出测试同时核对两种位置结果；测试 fixture 改用生产 UUID 格式。16 项恢复服务测试与差异检查通过。新字段尚未接页面、未部署，不提供自动完成或自动重试。

S4 隔离进程退出验证通过：在临时目录/独立 Python 解释器运行真实 RecoveryService._run，分别在发布前及真实 publish_capture 已 rename 后、最终回执前调用 os._exit(23)，绕过 finally。新服务实例同请求返回 needs_attention/publishing、不启动新线程、不写 recovered_run_id；候选副本分别留在暂存/目标目录，原始 fixture 字节和源 manifest 保持，查询不改旧日志。16 项恢复服务测试通过（0.13 秒），差异检查通过。本测试替换了原始数据复制/校验步骤为小 fixture，验证的是持久化与实际进程退出边界，不是生产桥接被终止、CARLA 崩溃或真实原始数据审计；没有中断线上服务。

S4 恢复响应一致性修复：核对 DataCollectionPage 已按 selected 设置 CaptureRecovery key，数据集切换会卸载旧实例，未重复添加隔离方案。新增 parseRecoveryJob 并同时用于启动响应和状态查询，拒绝请求/源录制错配、未知状态、成功缺副本、未成功却带 published ID、候选/发布 ID 不一致及非字符串展示字段；避免此前 POST 比 GET 宽松。新增 Node 解析专项、TypeScript 与差异检查通过。此为响应契约验证，不冒充浏览器切换/断网实测；未知请求的人工解除仍未实现。

S4 恢复页面网络控制修复：原 setInterval+无界 fetch 改为既有 serialPoll/readWithRetry（单次读、有界超时、卸载中止），核对 request_id/source_run_id/状态及恢复副本 ID。启动 POST 设置 30 秒超时，响应丢失/HTTP 错误不丢弃请求 ID、不自动重新创建副本，转 checking 只读查询并阻止再次提交；重新载入已保存请求也先 checking，不将本地缓存当作服务正在运行证据。数据集切换清空旧确认与任务显示。TypeScript、既有串行轮询及有界读取专项通过，差异检查通过；页面整体断网/切换竞态与服务不存在请求时的人工解除流程仍待验收/完善，不将工具级测试等同组件集成测试。

S4 恢复中断可追溯性开发：RecoveryService 新任务按 copies/request_id 隔离暂存，复制前持久化 copying/暂存位置，发布前持久化 publishing/candidate_run_id，完成后才写 published/recovered_run_id。网页展示暂存位置与候选 ID 并明确不证明发布成功。模拟新服务实例在发布意图已写后读取/重复提交同请求，得到 needs_attention 且不启动线程、不伪造成功；14 项恢复服务测试、TypeScript、差异检查通过。原共享暂存目录不迁移/不删除；最新隔离目录版本尚未重载桥接，未进行实际进程中断及网页新字段验收。

S4/S5 新恢复副本网页验收通过：选择 `recovered-4f6835a9ab294e358ef6ad40d0d1c1d3`，页面保留原 execution failed，明确说明恢复子集、排除 1 个未提交尾帧、不是完整录制。实际点击播放从 1/5 到 5/5，尾帧 241313、历史 5 点/未来 0 点，旧数据无预测契约时不画预测。网页发起原始数据校验并显示通过：5 个同步样本 RGB NPZ/米制深度/XYZI/BEV、14/14 外参。截图 `runs/validation/recovery-replay-warning-20260929.png`、`recovery-replay-cameras-20260929.png`、`recovery-replay-quality-20260929.png` 已查看；cameras 截图只覆盖完整前排及后排部分，不宣称该截图完整展示六路和 BEV。此轮未新增录制，仅新增质量报告与截图。网页“创建恢复副本”按钮及中途服务崩溃仍待验收。

S4 真实恢复服务发布与幂等验证通过：空闲检查及 PID/cwd/cmdline 核对后重载桥接，加载最新单目录/硬链接计量修复，不重启 CARLA、不换图。`regression_recovery_publication.py capture-20260910T165555-a6a12724` 核对源执行已停止，调用真实 HTTP 服务产生 saved_recovered 非空副本；源全文件清单/哈希不变，同一请求 ID 再提交返回同一 recovered_run_id，不新增副本，结束后 idle 通过。收据 `runs/validation/recovery-publication-dddbc525e13c4577bf9e9729d242e811.json`。恢复是保留已提交数据的副本，不把原失败运行标为成功；该轮未验收浏览器恢复按钮及恢复过程中服务崩溃。

S4 真实文件超配额发布拒绝通过：`regression_publish_quota_rejection.py` 复用上一轮 HTTP 锁拒绝保留的单帧暂存副本；确认空闲、录制目录完整计量且超过 1 GiB 后，仅本验证进程临时设置 CSA_CAPTURE_QUOTA_GIB=1，调用真实 publish_capture。按真实分配块数拒绝 quota reached，暂存全文件清单/哈希保持、目标目录不存在；finally 恢复验证进程配置，未改桥接环境、未新增传感器数据/副本、未删除数据。收据 `runs/validation/publish-quota-rejection-d4c39d27dfa94be5ad46419f32ac6e81.json`。这是生产函数+真实磁盘的集成验证，不是 HTTP 服务配额环境切换或磁盘耗尽验收。

最新完整回归：1526 passed，49.50 秒，无跳过；全部 Node 专项（含新增材质恢复网络契约）、TypeScript 与差异检查通过。新增单目录计量测试覆盖非法路径、缺目录、链接、损坏清单、缺 manifest 及显式扫描范围；修复选定非 capture 前缀目录缺 manifest 时误报完整零占用的问题。19 项存储专项通过。最近硬链接/选定目录计量修复尚未重载桥接，不能把本轮测试当作线上发布验收；八阶段门槛不变。

S4 发布占用计量硬链接边界修复：父目录全量扫描会跨兄弟录制去重 inode，若待发布副本与前一个未发布兄弟共享硬链接，其行 allocated_bytes 可能偏小。inventory_captures 新增受 identifier 校验的单目录扫描，publish_capture 仅测量待发布目录，内部仍按 inode 去重，不受兄弟暂存项影响。真实硬链接测试核对传给配额检查的分配字节数，拒绝后两份文件仍在；58 项存储/配额/服务测试通过（0.17 秒），差异检查通过。同一 inode 已在目标目录时可能保守多算，不冒充精确新增磁盘用量；目录元数据及外部写入仍不覆盖。本修复尚未重载桥接。

S4/S5 片段发布真实 HTTP 验收通过：新增 `regression_excerpt_admission.py`，复用两帧测试录制 `capture-20260929T133839-f89847ea` 选择单帧。正常任务 ready、raw_data_verified=true、发布 manifest.frame_count=1、ZIP 下载成功；持有采集写锁的第二任务明确 failed/admission lock，无已发布 excerpt_run_id、无目标目录，暂存副本保留，下载 HTTP 400 拒绝。每轮对原录制完整文件清单/哈希复核不变，任务结束后 idle 通过。收据 `runs/validation/excerpt-admission-5a587fb998be48499f1af3e0a381cb55.json`。未运行新仿真、未换图、未删除数据；锁拒绝不等于真实超配额拒绝，恢复服务与浏览器发布验收仍待完成。

S4 恢复/片段服务配额拒绝状态验证及部署：新增服务级 quota/busy 分支测试，确认发布失败状态为 failed、不返回 recovered_run_id/excerpt_run_id、不提供就绪下载，源 manifest 不变，暂存目录保留。48 项配额/恢复服务/片段服务测试通过（0.16 秒）。空闲检查与 PID/cwd/cmdline 核对后仅重启桥接加载改动，不重启 CARLA/不换图；重载后 idle 与 preflight ready=true 通过。此轮没有创建真实恢复/片段，真实 HTTP 发布与拒绝验收仍待执行；暂存/ZIP 总量和 CLI 写入覆盖未完成。

S4 恢复/片段发布接入采集写锁与配额：新增 publish_capture，在同一根写锁内检查目标不覆盖、测量已审核暂存副本分配块数、检查目标采集目录配额再 rename；RecoveryService/ExcerptService 的发布入口已调用。拒绝时保留暂存副本，不删除原数据。44 项配额/恢复服务/片段服务测试通过，涵盖锁竞争、配额不足、已有目标及成功发布的原始字节保持；差异检查通过。此轮未重启桥接，服务尚未加载这版发布逻辑；CLI 直接指定输出、暂存副本/ZIP、外部写者及全局清理事务仍未纳管，不能宣称全 runtime 原子配额完成。

S4 锁冲突后的短采集恢复实机通过：`regression_sensor_rig.py --short-stationary`（新增显式短验证模式，原默认 120 帧规则驾驶验收未缩减）。10 仿真帧/每 5 帧保存一次，录制 `capture-20260929T133839-f89847ea` 共 2 样本；完整数据校验通过 RGB 原始数组、米制深度、XYZI、BEV，14/14 外参、地图投影与时间间隔验证通过，重复启动拒绝。无采集错误、无清理错误；同一 episode 4772444009943974257 / Town04，结束后 5 秒 21 次观察为异步且传感器 0。收据 `runs/validation/sensor-rig-962c5a82724947d6b4cebf5fa56f5bdf.json`。未换图/重启 CARLA；此为 2 样本恢复冒烟，不是长录制或规则驾驶表现验收。客户端 dirty 版本差异警告保留。

S4 采集写锁冲突实机通过：`tools/regression_capture_lock.py` 在空闲 Town04 持有采集根写锁，经真实桥接启动 10 帧 stationary 独立采集；会话明确 failed、worker error 含 Another capture writer holds admission lock、stop_reason=capture_io_error、recorded_frames=0、cleanup_errors=[]。对应 manifest 为 saved_capture_error、frame_count=0、execution_id 匹配，index.frames=[]。退出后独立 CARLA 检查无传感器、无 sensor_rig 车辆、世界异步，idle 与 preflight ready 通过；未换图或重启 CARLA。收据 `runs/validation/capture-lock-5907216d9af84ed582bc0ad9d551b5ec.json`。这是受控锁竞争而非真实磁盘耗尽或服务崩溃；已有样本保留和故障后正常再次采集尚需另测。新 worker 从当前源码加载改动；桥接本身没有重启。保留客户端 dirty 版本差异警告。

S4 独立采集失败报告遗漏已修复：run_sensor_rig 的 process_frame 抛错可能先于正常帧报告更新，原 finally 仅写 cleanup_errors，会遗漏本次录制 ID/已保存数/原始错误。新增异常分支在清理前记录原始 error、capture_error、stop_reason、run_id 和实际 capture.count，并重新抛出保留失败退出；不把失败帧计入正常处理帧数。使用现有 worker main 的隔离模拟依赖测试注入写锁竞争，确认错误报告与清理顺序（capture.close→销毁车→恢复设置）；注册失败路径仍通过。worker/配额专项共 27 passed（0.13 秒），差异检查通过；非真实 CARLA 验收、尚未部署。

S4 采集锁跨进程测试通过：新建独立 Python 解释器取得临时目录写锁，父进程确认子进程仍存活时竞争获取被拒；分别让子进程正常退出、在持锁期间 os._exit(17) 绕过 finally 退出，之后均能重新获取同一 inode 的锁。测试不操作现有录制或仿真进程。配额专项 23 passed（0.11 秒）及差异检查通过。此项证明本机协作锁的进程隔离与退出释放，不等于所有数据生产工具纳管或实机配额验收。锁竞争走现有 capture_io_error 异常向 owner 传播，具体会话停止/清理行为仍需实机核验。

上述采集锁修正后的配额/采集专项重跑：77 passed，41.14 秒，包含原有 NPZ/PNG/索引/manifest 写盘失败矩阵；差异格式检查通过。未重新全量回归、未部署，不替代多进程及实机验收。

S4 配额写入互斥开发：SensorCapture 将配额读取、单样本写盘和索引/manifest 提交置于同一根目录 flock 锁内。锁非阻塞，竞争时抛出明确写入错误交由既有录制停止处理，不等待而阻塞 tick；拒绝符号链接锁，不删除锁文件以免 inode 分裂。覆盖范围仅协作 SensorCapture，恢复/片段/归档及外部写者尚未接入，不标为全局原子配额完成。新增竞争、异常释放、inode 保持及链接拒绝测试。首次重构因 safe 局部函数作用域遗漏导致 40 项采集测试失败，已将 input_scalars 转换保留在原作用域修正。尚未部署或实机验收。

S4 验收数据保留登记已落盘：使用新增 `protect_reviewed_capture_baselines.py --execute` 将人工驾驶/看门狗/事件基线 `capture-20260908T131711-80c015a7` 和 UniAD 类名识别失败反例 `capture-20260910T180331-b461bbb2` 纳入 CaptureRetention，revision=20。写入前核对原文档引用和录制身份，已有标记不覆盖；重复执行显示 preserved_existing_marker、不增加 revision。两项测试覆盖只读预览、执行幂等及第二项证据缺失时零写入。未删除原始数据、未释放空间；这使已核实用途可由后续清理程序读取，不再仅依赖文档文字。

清理引用阻碍复核：项目包扫描 43 项、reference_scan_complete=true、scan_errors=[]；7 项为旧格式/暂存警告，不是引用扫描失败。此前将它们概括成清理阻碍不够准确，已在汇总文档纠正。盘点输出新增本地引用扫描完整性与明确 deletion_approved=false，保留原 complete/warnings。34 项引用测试通过；新收据 `/tmp/safeagent-storage-reference-audit-20260929.json`，219 份/89.789825 GiB 未变。两个大候选经文档核实分别是人工驾驶/看门狗/事件回放基线及 UniAD 预测识别失败样本，继续保留。本轮未删除，不声称释放空间。

S2/S3 恢复请求网络契约已抽取并接入真实按钮：超时覆盖 fetch 和响应体解析，超时主动中止且结果标为未知；不自动重发写请求。新增 `tools/test_material_recovery_request.mjs` 覆盖精确请求参数、身份/目标/状态错配、网络丢失、HTTP 错误、坏 JSON、请求无响应和响应体不结束，每个已发起分支只调用一次；无有效检查时零调用。测试使用注入 fetch，不冒充浏览器/真实网络故障验收。专项、TypeScript 与差异检查通过，完整网页延迟/超时流程仍待实测。

S2/S3 恢复请求中刷新防护已实现：MaterialRecovery 在请求前/结束后上报 pending；MaterialInspection 同步 ref 拦截及禁用只读刷新，EditorHistory 按操作 ID 集合追踪未结束恢复，拦截手动刷新和其他操作 onDone 触发的刷新，避免单个请求完成误解除另一请求的保护。超时后允许检查，但原恢复按钮仍保持 used、不自动重提。TypeScript、材质检查专项及差异检查通过；真实浏览器延迟/超时交互尚未验收。此保护仅覆盖当前组件内刷新，不承诺阻止整页导航、浏览器刷新或其他标签操作，后端身份/token 校验继续作为修改保护。

最新完整回归：1499 passed，49.66 秒，无跳过；全部 `tools/test_*.mjs`、TypeScript、生产构建及 `git diff --check` 通过。构建仍有 vinext Unknown 路由分类提示。此轮未重新运行模型。代码检查确认待修网页交互：MaterialInspection 的只读检查和上层 EditorHistory 刷新未与 MaterialRecovery 的请求中状态联动，可能卸载正在提交的控件；后端 token/recovery 校验防止重复修改，但页面请求状态和多标签/超时流程尚不能视作验收通过。

S2/S3 恢复回执网页展示已补齐并实际查看：材质检查解析器验证恢复状态、选择与目标哈希一致性；展示原失败与后续恢复分别存在，并比较当前登记是否仍等于恢复目标，不把历史恢复成功当作当前状态。Node 专项、TypeScript 与差异检查通过。浏览器只读检查真实已恢复记录 `daddc2d73f0e4ca39778e37163c8cf63`，显示原失败保留、恢复原材质已确认、当前登记一致；截图 `runs/validation/material-recovery-receipt-browser-20260929.png` 已查看。此轮没有提交恢复写入，网页恢复按钮实际执行和恢复失败后的后续处理仍未验收。

S2/S3 显式材质恢复已部署并通过受控实机测试：`regression_material_history.py --recovery`，收据 `runs/validation/material-history-a8b2fc9a62e94b37aad6066d3c3b949c/report.json`。真实 HTTP 应用后由测试回调主动报错（不是 CARLA/桥接崩溃）；检查当前登记为 target，显式恢复 source=null 成功，原 needs_attention/error 保留，重复恢复请求返回 400。已查看 injected-failure.jpg 与 explicit-recovery.jpg：教堂品红墙面恢复原材质，屋顶与窗户未见改变；相机恢复。235 项材质/桥接测试通过。首次收据 `material-history-37615c9463c14496a0bf60f9836cb556` 保留失败：恢复已成功，但测试 finally 重复恢复无覆盖槽，原生接口报告 original material not recorded；已改为无覆盖时只核查截图，再跑通过。首次多余调用产生的失败日志也未删除。网页故障恢复点击、真实服务崩溃与重复恢复失败处理仍待验收；不能据本次宣布 S2/S3 完成。

S2/S3 网页显式材质恢复控件已接入代码：只在最新检查包含有效 token、未解决状态且无既有恢复记录时显示；先选 source/target，再核对目标哈希并勾选确认才可提交。请求携带检查时登记值，响应核验操作/选择/哈希；一次提交后禁用，提示重新检查而非自动重试。原失败记录保留，成功仅表示恢复写入确认。Node 检查解析测试、TypeScript、差异检查通过。恢复 HTTP 版本仍未部署，网页与实机故障恢复未验收。

S2/S3 显式材质恢复 HTTP 接入（未部署）：新增 `/materials/history-recover`，严格要求 operation_id、inspection_token、source/target 选择、检查时登记值及 confirmed=true；检查独占空闲，复用材质历史相同的 episode/目标/UV0 槽/当前引用/目标纹理校验与精确原生写入。成功返回独立 recovery，不改变原始失败状态，仍提示需视觉验证。235 项材质与桥接测试通过，包含登记值错配零调用、精确槽应用、原失败保留、重复提交拒绝。网页恢复控件和实机故障恢复验收仍待完成。

S2/S3 材质显式失败恢复核心开发（未接 HTTP/网页）：只读检查增加日志内容哈希 token；恢复要求当前未解决记录、精确 token、明确 source/target 选择和检查时登记值。verify 在任何恢复写入前核对，之后写 recovery intent、执行指定纹理写入、记录独立恢复结果；原始失败 state/error/pending 保留，不伪造当时成功。恢复未知结果或旧 token 不允许直接重复提交。15 项材质历史测试通过，含原错误保留、过期 token、登记变化不写入验证。尚未部署、未实机验收，重复恢复失败后的后续处理仍待设计。

S2/S3 材质只读检查已部署并网页实测：HTTP 对记录 `1f630710abb740058f70f7bba7318130` 返回 target 匹配、当前无覆盖，检查前后日志字节一致。浏览器实际检查最新恢复记录 `af3193bccfed44a6bb8751b569d8ffcd`，显示“登记引用与操作目标一致”、无覆盖及不验证 GPU/不改历史/不自动重试说明。截图 `runs/validation/material-inspection-browser-result-20260929.png` 已查看（另一张 overview 截图未覆盖结果下半部分）。未改场景材质、不换图。失败记录的显式恢复流程仍未完成。

S2/S3 网页材质只读检查入口已实现：统一历史每条环境材质记录提供当前登记检查，展示 source/target/both/neither 及三方纹理引用，明确不验证 GPU、不改写历史、不解除阻塞。前端校验 operation ID、纹理哈希、比较结果和验证范围；可超时重试只读请求，组件卸载取消请求。专项 Node 解析测试、TypeScript、差异检查通过。检查接口尚未部署，网页点击尚未实测，显式失败恢复仍待开发。

S2/S3 材质失败检查接口开发（未部署）：新增 `/materials/history-inspection`，在相同 episode/环境目标下比较当前登记纹理与操作 source/target，返回 source/target/both/neither；待检查撤销使用 pending 的实际方向。该接口只读、不改写失败日志、不解除阻塞，明确 native_verified=false / automatic_retry_allowed=false；登记哈希吻合不代表 GPU 状态已确认。232 项材质模块与桥接测试通过，含检查前后原始日志字节不变验证。尚无网页检查入口及显式失败恢复流程。

S2/S3 真实 HTTP 并发材质撤销通过：`regression_material_history.py --concurrent` 同时发送两个相同 operation/revision 的撤销请求，结果恰为一个 200、一个 400，持久化 transitions 只有一条；随后重做成功，清理恢复原材质并恢复相机。收据 `runs/validation/material-history-e275c424ca9645cbb5e507f878b704bb/report.json`。该测试验证真实服务并发提交及状态转换，不等同于浏览器多标签的确认状态/网络丢包 UI 验收。

最新全量后端回归：1492 passed，49.04 秒，无跳过；全部 `tools/test_*.mjs` 脚本通过。此结果更新下方旧的回归数量，但不替代仍缺失的实机/故障验收。

S2 编辑历史故障测试增量：同一 MaterialHistory/CopyHistory 实例的双线程并发撤销，只有一次原生应用/删除；材质转换意图落盘失败则不调用原生操作，提交失败则保留 needs_attention，提交与失败回执均不可写则保留 attempting；后两者均拒绝直接重试，不误报成功。18 项材质/复制模块测试通过，全部 Node 专项脚本通过。范围为后端线程与注入式磁盘故障，不代表浏览器多标签、跨进程或真实磁盘耗尽全链路验收。

S2/S3 网页材质撤销重做实际点击通过：对测试恢复记录 `1f630710abb740058f70f7bba7318130`，浏览器勾选并撤销，后台核实恢复品红纹理哈希 `e757946f293f998994483a3daf81d8c4cb0b526e50c85df8f0a3e20a9f418212`；再勾选重做，覆盖表清空、历史 applied=true/transitions=2，ready=true。网页显示环境对象 ID `1077430972180586611` 无精度丢失。截图 `runs/validation/material-history-browser-undo-20260929.png`、`material-history-browser-redo-20260929.png` 已查看。此轮验证页面与后端记录；实景颜色证据沿用此前单独实机测试，不声称这两张网页截图展示实景。跨页面竞争与外部未纳管修改仍未全面验收。

S2/S3 网页材质撤销重做已接入代码：统一历史展示本次恢复目标哈希或移除覆盖；确认勾选后携带 operation_id/revision/direction 提交，成功校验操作身份、新 revision 和应用状态后刷新。待检查记录不提供操作，未知响应锁定本组件直至重新读取历史。不把旧记录当成当前槽位状态，后台仍执行登记纹理一致性检查。Node 解析及 TypeScript、差异检查通过；网页真实点击验收尚未完成。

S2/S3 材质历史已部署并完成代表实机验收：`regression_material_history.py` 在无已有覆盖的 SM_Church01_5 / StaticMeshComponent0 / 槽 0 应用青色 A、品红 B，撤销 B 返回 A 哈希，重做返回 B 哈希，旧 revision 请求 HTTP 400 拒绝。收据及截图：`runs/validation/material-history-b5af05d090d84e63afe7ef28c99e125a/`。已查看 undo/redo/restored.jpg，墙面青色→品红→原材质可见，屋顶与窗户保持；最后覆盖记录为空、相机恢复。此为单代表槽正常流程，不外推道路/所有资产、故障矩阵或网页材质撤销验收；网页操作按钮仍待接入。

S2/S3 环境材质撤销重做后端开发（未部署）：新增 `/materials/history`，绑定操作与 revision，核对 episode、环境目标、UV0 槽及当前工作台登记纹理；不匹配拒绝覆盖，预读目标纹理校验后才写操作意图。撤销恢复 before 哈希而非一律恢复原材质；重做恢复 after 哈希，保留最多 100 次转换记录。调用结果不确定时保留 pending 并禁止继续重试。233 项相关测试与 Node 解析测试通过。尚未部署/实机验证，网页尚无材质撤销按钮；外部未纳管的 GPU 材质修改不可由本登记表检测，不宣称覆盖该情形。

S2/S3 材质日志汇总已接入代码：统一历史 API 可读取精确环境槽日志，网页展示环境对象 ID、episode、组件、槽和前后纹理哈希/null 原材质引用；环境 ID 作为字符串传递，测试覆盖 uint64 最大值而不转 JS number。12 项历史/材质模块测试、Node 解析、TypeScript 和差异检查通过。桥接尚未加载这版材质日志，未实机验收；纹理撤销重做及车辆/行人入口纳管仍待完成。

S2/S3 精确环境材质历史开发（未部署）：`apply_material_slot` 接入写前日志，保存 episode、环境对象 ID、精确目标/组件/槽以及修改前后纹理哈希；恢复原材质记录 after=null，不把它伪作撤销上一步。原生调用或引用落盘失败保留 needs_attention，不自动重试。日志成功仅说明调用与引用记录完成，不声称直接读取 GPU 材质状态。新增模块与桥接集成测试通过；未接入统一历史查询、未提供纹理撤销重做、未实机验收，车辆/行人旧应用入口尚未纳入该日志。

S2/S3 带纹理副本撤销重做实机通过：`regression_duplicate_texture.py --redo` 及 `--redo --pedestrian`。Audi A2 的 VehicleMesh 槽 4、walker.pedestrian.0001 的 CharacterMesh0 槽 14，在恢复后保持副本 stable ID 和完整 actor_materials（包括纹理哈希），源对象记录未改。证据分别为 `runs/validation/duplicate-texture-44439fee4da4458b9e8824fbf42975cb/`、`runs/validation/duplicate-texture-5be6128f4ffe472ca7b8d08e13913085/`。人工查看两组 source.jpg/duplicate.jpg：车辆后轮拱彩色标记、行人裤装棋盘格可见且对应；不是逐像素比较，也不代表整车纹理设计或其他资产覆盖完成。原始 report.json 的 visual_review=pending 保留，本段补记后续图像查看结论。六个临时 actor 1084/1085/1086/1089/1090/1091 已由独立世界快照确认不存在，观察相机恢复，ready=true。统一纹理操作历史仍待开发。

S2 网页重做与再次撤销实测通过：使用测试复制记录 `2c0c2fee1c9f4399821a02b2a21c2437`，在浏览器核对备份并勾选重做，恢复为 actor 1083，稳定 ID `34cacfff98ce477c9b7d388f503da95c` 保留。页面刷新后显示新副本及撤销入口，再经检查/确认撤销成功；持久化 cycles=1、当前 undo=confirmed。独立世界快照确认 1077/1078/1083 均不存在，ready=true。截图 `runs/validation/copy-redo-browser-confirm-20260929.png` 与 `runs/validation/copy-redo-browser-result-20260929.png` 已查看。该正常网页循环已验证；多标签竞争、超时恢复、材质覆盖副本与统一纹理历史仍未完成。

S2 网页重做入口已接入代码：已撤销复制显示目标稳定 ID、精确备份场景与版本，明确勾选后调用 `/objects/copy-redo`，携带当前删除操作 ID；成功校验返回副本身份并刷新历史，错误/未知响应禁止本组件直接重复提交。保留独立单对象恢复作为备用入口，并标明不改写复制历史。Node 解析测试、TypeScript 与差异检查通过；网页重做实际点击尚未验收，不能以此前 API 实测替代。

S2 复制重做已部署并通过实机正常循环：`regression_duplicate_collision.py --redo` 收据 `runs/validation/duplicate-collision-e5224f44c6684a398c04052ca024d708.json`。源 1079、占位 1080，副本 1081 撤销后从精确备份恢复为 1082，稳定 ID `caf03a84fb3847df8967c5ce35264902` 保留；重复重做被拒绝，再次撤销删除 1082，原循环保留在 cycles。两次撤销期间源/占位对象均仍在世界快照中，最后清理测试源/占位对象，空闲与 ready=true 复核通过。不重启 CARLA、不换图。尚未有网页重做按钮，材质覆盖副本、多轮压力及异常恢复未实机验收。

S2 复制重做状态机开发（未部署）：新增 `/objects/copy-redo`，绑定当前撤销的删除操作 ID，从该次精确备份恢复，拒绝跨 episode 和稳定 ID 已存在的对象；成功后更新副本运行时身份，将上一轮目标/撤销/重做记录保留在 cycles 中，可再次撤销。重做前写意图，未知结果保留待检查并禁止直接重试。当前限制每条复制记录 50 个完整循环，达到上限明确拒绝，不截断旧记录。234 项相关后端测试、Node 解析、TypeScript、差异检查通过；未部署、未实机验证、尚无网页重做按钮，不视为阶段完成。

S2 副本恢复入口：统一历史的已撤销复制记录现可选择其删除前精确场景版本，转入现有单对象恢复区，不重新复制当前源对象。前端校验删除响应 actor ID、备份 stable ID 与复制目标一致，不匹配时拒绝解析。恢复需再次选择目标与明确确认；该入口不会把历史状态伪改成“已重做”，完整可重复撤销/重做状态机仍未实现。Node 解析测试、TypeScript、差异检查通过；新入口浏览器操作尚未验收。

S2 网页撤销复制实测通过：操作 `2c0c2fee1c9f4399821a02b2a21c2437`，临时源 1077、副本 1078。浏览器实际打开历史、检查副本、核对位置、勾选确认并撤销；勾选前确认按钮禁用，提交后显示“已撤销”及独立删除记录。截图 `runs/validation/copy-undo-browser-review-20260929.png` 与 `runs/validation/copy-undo-browser-result-20260929.png` 已查看。独立 CARLA 世界快照确认源保留、副本不存在；复制日志撤销状态 confirmed，删除备份 `e2ecf3dd077b48668445bca11f1e184f`。最后仅清理本次临时源 1077，确认两个测试对象均不存在、ready=true。此为正常路径网页验收，不覆盖网页超时/多标签竞争；复制重做及纹理历史未完成。

S2 网页撤销复制增量：统一历史中已确认且有目标身份的复制记录提供“检查副本以撤销”，调用现有实时变换检查，匹配 episode/actor/type/stable ID 并显示位置；明确勾选后才提交撤销。提示副本后续修改随副本删除、删除前保存备份。错误或未知响应清空确认，不自动重试；完成后刷新历史。新增身份错配/无效位姿解析测试与 TypeScript 检查通过。尚未完成浏览器真实点击验收，不声称网页端验收完成；重做及纹理历史仍待开发。

S2 撤销复制实机验收：已部署 `/objects/copy-undo`。真实临时车辆测试通过错误位置审阅拒绝（日志未变）、正确撤销及删除备份、源对象/占位对象保留、重复撤销拒绝。收据 `runs/validation/duplicate-collision-0dc4103d2c8a4d9c8db47d98ef0537e2.json`；测试对象已清理，空闲与 ready=true 已复核。前两轮失败收据 `duplicate-collision-66b2e695c229472e92f2538a537e5391.json`、`duplicate-collision-9980f91c7d9a4ee99f8b236c0a014252.json` 保留：测试误用 `get_actor` 缓存描述判断存活。本机 LibCarla Episode.cpp 的 GetActorById 缓存路径证实该判据不可靠，改用世界快照与活动对象列表；成功轮同帧记录 target_present=false / cached_lookup_present=true。未更改实际删除逻辑以迁就测试。网页撤销按钮、重做与统一纹理历史仍待实现；此轮未重新全量测试。

S2 撤销复制开发（未部署/未实机验收）：新增 `/objects/copy-undo`，要求明确确认和当前目标位置审阅；校验世界 episode、actor 类型及稳定 ID，只通过现有备份删除链路删除副本。写前保存撤销意图，结果不确定时保留待检查状态并拒绝重复执行；源对象不参与删除。统一历史页面识别撤销成功/待检查状态。232 项相关后端测试、Node 解析测试、TypeScript 与差异检查通过。尚无网页撤销按钮，尚未完成重做与完整统一历史；运行中桥接仍为仅复制日志版本。

最新全量回归：复制日志部署后执行 `PYTHONPATH=src python3 -m pytest -q tests`，1474 passed，49.23 秒，无跳过。此数替代下文此前 1462 项记录，不替代各阶段实机验收。

S2 复制日志实机增量：已空闲重启桥接加载新实现，不重启 CARLA、不换图。碰撞占位测试中源对象 1065、占位对象 1066、副本 1067；第二候选位置成功且仅新增一个对象，复制日志源/目标稳定 ID 不同，磁盘记录与统一历史 API 一致。收据 `runs/validation/duplicate-collision-033aa5c4b43343d9943236821cdc4245.json`。测试后三个临时对象均确认不存在，ready=true、异步模式；生产构建通过，保留客户端 dirty 版本差异和 vinext Unknown 提示。此证据不代表复制撤销或所有崩溃分支完成。

S2 复制日志增量（未部署）：本地编辑器复制增加写前意图、源对象与新对象身份、原生返回 ID 及需要检查状态；统一历史 API/页面支持复制记录。评测进程内复制、旧历史补录及复制撤销尚未覆盖。新模块与桥接相关测试通过，TypeScript、Node 解析和差异格式检查通过；运行中的桥接仍为上一版，不将此次单测当作实机验收。

S2 后续开发：新增 `/objects/edit-history` 只读统一查询，将当前变换链、待检查变换意图和删除记录汇总，返回覆盖范围与坏记录警告，不伪造旧意图时间、不自动批准撤销。36 项相关测试通过；直接读取现有持久化数据得到 23 条记录、无解析警告。已在空闲检查后重启桥接（不重启 CARLA、不换图），接入项目面板；浏览器实际点击读取返回 23 条，待检查操作置顶并明确标注无时间，截图 `runs/validation/editor-history-browser-20260929.png` 已查看。新增 Node 解析测试、TypeScript 与生产构建通过（保留 vinext Unknown 路由提示）。复制/纹理记录、统一撤销重做仍待完成；本轮未重新执行全量测试。

本次只读重新盘点：219 份录制，实际分配 89.78983 GiB；`du` 显示 `.runtime/generated-scenarios` 约 91G，整个 `.runtime` 约 102G（范围与取整不同）。收据：`/tmp/safeagent-storage-review-current.json`。

本次没有追加删除。最大的 5.16 GiB 录制是唯一 400 帧规则场景/旧回放兼容性基线；其余多个大录制已有明确保留标记，部分中断录制被恢复数据引用。项目扫描仍有 7 项旧格式/暂存警告，不能据未标记或年代久远推断可删。下方 216 份、89.52 GiB 为历史快照，不是实时容量。

## 当日后续已验证增量（优先于下表早期状态）

- TCP路线26406已自然完成100%，健康退出、异步恢复、零残留传感器；驾驶分2.79936，7条车辆碰撞与20条低速违规，因此不是安全驾驶通过。其余模型长路线及完整崩溃矩阵仍待验收。
- 五种公开模型的预设路线预测来源观测已实机通过，保留来源帧与复用信息；TCP三帧录制保存、API轨迹读取和网页播放已通过。时间间隔与ADE/FDE仍未验证。
- 修复录制与人工驾驶路由冲突；录制改用独立接口，严格参数校验、执行ID绑定、会话锁和进程侧旧命令隔离已接入。实机错误ID开始/停止均拒绝且命令文件不变，正确ID保存3帧成功；浏览器并发故障仍未全验收。
- 最新回归1462项后端测试全部通过（49.49秒、无跳过）；21个Node专项、TypeScript、生产构建及git diff --check通过。保留vinext路由分类Unknown提示。
- 为验证实际保存链路，新增了3份各3帧的小录制，每份约93 MiB；下文89.52 GiB为此前盘点，不再当作当前实时容量。未再次删除数据。

八阶段仍未全部完成。统一编辑历史、全阶段故障矩阵、跨机迁移和最新GitHub交付等原待办不因这些增量而关闭。

本表归并原计划与现有验收记录；本次核对没有重新运行模型。八阶段都有已实现功能，但没有一个阶段满足全部验收门槛，不能把短闭环通过写成全系统完成。

| 原计划 | 已实现且有验证记录 | 尚未完成 |
|---|---|---|
| S1 稳定性 | 会话独占、启动预检、停止恢复；原生 RPC 关闭错误候选修复部署；VAD/TCP/ADMLP/UniAD tiny/base 短闭环；实验模型受控换图；TCP 一条路线自然完成 | 其他模型长路线、持续压力与完整服务崩溃矩阵；不能承诺不再崩溃 |
| S2 场景持久化 | 来源与稳定 ID、场景版本、变换历史、隐藏及代表材质持久化；删除备份、历史查询、单对象恢复；生成对象参数与代表纹理复制 | 复制/删除/纹理统一撤销重做、完整失败补偿矩阵 |
| S3 精准材质 | 代表车辆、行人、建筑、道路、长椅的真实网格/UV/槽验证；车辆及行人纹理复制近景核对 | 未支持资产扩展、完整预览实景一致性及剩余视觉问题；不是任意对象都支持 |
| S4 统一采集 | 独立/人工/规则/模型采集；六辅助 RGB、深度、点云、标定、模型实际输入；质量检查、归档、录制配额、数据划分登记引用保护 | 全局原子配额和清理事务、长录制压力、划分上传网页验收 |
| S5 回放诊断 | 同步多视角、深度/点云、真值与空间预测、事件片段、ROS 九路布局、离线回放；录制保存状态与执行失败分开显示 | 预测时间契约、可靠 ADE/FDE、完整 TF/几何及吞吐验收 |
| S6 自然语言闭环 | 结构化计划、修改与确认执行；基本 Blender→Unreal→Blueprint→CARLA 链路 | 跨工具完整事务回滚、复杂资产生成扩展；不支持任意道路地图生成 |
| S7 批量实验 | 队列、重试、不可覆盖历史、配置追溯、纹理 A/B；20 份真实账本的 8 组比较只读审计通过 | 完整四维组合及故障矩阵、长任务/驾驶表现验收；最新比较字段网页验收 |
| S8 打包迁移 | 项目/资产包、路径诊断、注册重映射、同机隔离恢复；严格源码导出拒绝遗漏未提交源码 | 最新源码提交归档、跨机环境/引擎重建、GitHub 推送 |

边界：辅助六视角并非每种算法的原始输入；顶视 RGB 并非语义 BEV；ThinkTwice/DriveAdapter 受控验证不等于公开入口开放。最近一次完整后端回归记录为 1462 passed，本次状态盘点未重新运行测试。GitHub 尚未完成最新交付。

## 清理核对

- 当前重新盘点：216 份录制，实际分配 **89.51548 GiB**；整个 `.runtime` 的 du 显示约 **101G**，二者不是同一范围。
- 最近清理记录：六份中间崩溃调试录制约 4.391 GiB，以及一份被中断的 ThinkTwice 观察录制约 2.114 GiB；合计约 6.505 GiB。这是已执行的历史清理，不是本次重新盘点又释放的空间。
- 后者收据：`runs/validation/debug-cleanup-d790537b0d77465db85e7e77e2c3c5ef/`。保留元数据、哈希和执行日志；已删除的原始图片、深度、点云不可恢复。
- 本次盘点收据：`/tmp/safeagent-storage-review-20260929.json`。本次未追加删除；保留现用基线、唯一故障证据、项目/队列/划分引用、恢复源和用途未确认的数据。
- 仍有 7 项旧格式/暂存项目警告，不能把“未标记保留”直接等同于无用。后续仅清理有明确替代证据且重新通过空闲、引用、保留检查的精确目录。

## 推进顺序

1. 稳定性与数据安全：长路线自然完成、服务异常恢复、配额/清理边界。
2. 补齐编辑闭环：统一操作历史，扩展精确材质覆盖与实景核对。
3. 完成批量比较与回放诊断验收，再扩展自然语言复杂生成。
4. 最后进行跨机迁移验收、整理提交及经授权的 GitHub 推送。

原始验收门槛见 `DEVELOPMENT_PLAN.md`，逐项证据见 `PLAN_STATUS_LATEST.md`；不以新增扩展能力替代原门槛。

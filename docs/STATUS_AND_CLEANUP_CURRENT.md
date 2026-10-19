# 开发与清理状态（2026-09-29 本次核查）

原计划：DEVELOPMENT_PLAN.md。以下实现状态来自既有验收记录，本次未重新启动仿真或执行模型测试。八阶段均未全部验收。

## 最新核查摘要（取代下方历史时点描述）

- 6条旧导入记录实际审查迁移已完成：在维护/导入双排他锁内重新检查正式任务空闲、精确未解决集合、旧协调进程/产物/日志哈希，独立回执全部写入，逐项原日志字节不变。本地restart_status unresolved=[]；原6条needs_attention不变，仅单列reviewed_prelaunch_rejection。没有删数据、改资产、重启CARLA或桥接；旧服务无新资产状态端点的首次部署兼容尚待处理。证据见BRIDGE_DEPLOYMENT_REVIEW.md及各job/restart-review-<attempt>.json。

- 旧资产审查回执机制已实现：独立restart-review文件绑定原日志SHA256、job/attempt，要求精确旧版重名拒绝结构、有效结束时间、历史协调进程不再存在、无该attempt的原生请求/结果产物；每次读取重验这些条件，原日志或产物变化则拒绝。回执明确asset_success=false/automatic_retry=false，不修改原needs_attention；restart_status可据此将已审查的启动前拒绝单列。哈希变化、活协调进程、额外产物拒绝及原文件不变测试通过，资产相关100 passed。尚未对生产6条旧日志写审查回执或重启，记录工具的调用需在维护锁下重新核对空闲。

- 录制搜索补齐真实模型字段：核对list_datasets原样返回manifest.model/family，DriveAdapter现有录制确有driveadapter-experimental标识；搜索现纳入这两个字段，下拉显示保存的模型名。sensor-rig无模型明确标注独立采集，其余缺字段显示模型未记录，不按场景名推测模型。Node测试同场景VAD/DriveAdapter可区分及空/异常模型字段，TypeScript通过。未重新进行该增量的浏览器验收，不更改原始manifest。

- 质量终态缓存修复：成功持久化报告后移除transient终态缓存，后续读取磁盘最新报告；写盘失败仍保留本实例incomplete诊断。双实例真实临时文件测试：A检查passed，B开启新任务后A不再显示旧passed，B保存failed/frame42后A读取同一新失败。质量相关35 passed，diff检查通过。正式服务未部署，不能外推跨进程崩溃及所有旧实例兼容已验收。

- 录制搜索浏览器验收：实际222条清单，选中capture-20260929T161825-9e1187fd后输入no-match-acceptance，页面显示匹配0/222及“当前回放不匹配，仍保留选中”；下拉保持同ID，回放仍1/2帧、frame149143，历史质量报告及传感器画面保持该数据。截图runs/validation/dataset-search-retained-20260929.png已查看，搜索输入、数量提示、下拉和播放入口可见。未启动采集/修改数据；多条件匹配已有Node测试，尚未全部浏览器覆盖。

- 数据列表搜索已接前端：按场景名称、run_id、状态、地图大小写不敏感匹配，空格分词全部满足；显示匹配数/总数。当前回放不匹配时仍保留其选项并明确提示，不调用setSelected、不意外切回实时或切换数据。Node覆盖多条件、失败录制、零匹配保留、已删除ID、空查询及原列表不变，TypeScript通过。未浏览器验收，本功能不新增/删除数据或改变原始录制状态。

- 质量锁独立子进程验收：真实Python子进程继承服务scan.lock，父侧关闭描述符后子进程仍活着，另一QualityService.start拒绝且pending报告字节不变；子进程stdin结束、退出0后重试可启动并释放。另用真实audit_capture启动临时validator，通过os.fstat确认描述符确实传入。质量专项34 passed，未操作生产服务；这是存活子进程持锁机制验证，不是实际桥接SIGKILL或完整原始数据扫描崩溃验收。

- 质量扫描跨实例写保护：启动前取得reports/scan.lock排他锁，覆盖写入running、外部校验、最终报告，写盘/启动异常释放锁；校验器通过pass_fds继承，防止协调进程退出后仍运行的检查失去保护。两个真实服务实例共享临时目录测试确认第二次启动拒绝且原报告不变，首任务结束后可重新启动；质量相关32 passed。当前为同进程不同实例文件锁验证，独立进程存活继承和生产部署待验收；不覆盖旧服务或其他类型数据任务。

- 质量任务启动记录持久化：启动线程前durable_write保存running，已有报告先独立归档到history；最终报告也采用持久原子写。新服务读到未归属本实例的running时只读返回incomplete/validation_interrupted，不退回旧passed、不改磁盘、不自动重试、不声称旧子进程已死亡。测试确认旧通过报告归档保留、查询不改pending；初始写入失败不启动线程。质量相关31 passed。未部署、未做真实桥接进程中断验收；旧校验子进程的跨实例并发互斥仍待完善。

- 异常录制质量诊断入口修复：QualityService此前接受saved_cleanup_error却拒绝saved_capture_error，现允许已结束的采集失败数据执行只读验收，recording/recovery_pending仍拒绝。真实validator子进程通过服务扫描零样本失败录制，结果明确failed/no_samples、任务释放、manifest原始失败状态和error字节不变；回归含恢复/清理失败入口，质量服务及审计29 passed。质量通过也不意味着录制执行成功，沿用页面独立显示录制结果；未部署到常驻桥接，尚未实机页面启动此分支。

- 最新跨模块完整回归：后端1751 passed（58.63秒）；全部tools/test_*.mjs、TypeScript、生产构建、git diff --check通过。构建保留vinext路由Unknown分类提示。覆盖截至本次的位姿质量校验、结构化问题帧、报告清单新鲜度、资产锁与生命周期等代码；不能替代旧桥接未加载模块的正式部署、失败页面、跨机或多模型长路线验收。八阶段仍全部保持进行中。

- 质量历史新鲜度：页面按dataset key重新挂载已有保护，未重复修改；后端status新增manifest_freshness只读比较历史哈希与当前清单，覆盖内存报告和服务重启后磁盘报告，原state/文件不改写。清单改变时前端明确提示历史结果不代表当前质量、需重新检查；清单未变也不证明原始传感器文件未变。质量服务6 passed、Node报告解析和TypeScript通过，未部署或做清单篡改实机/浏览器测试。

- 原始质量正常报告浏览器验收：实际打开localhost:3000→Collect Data→选择capture-20260929T161825-9e1187fd→展开校验日志，页面显示“本次检查通过”、2同步样本、14/14外参；保留“不代表驾驶安全”和历史报告需重新检查说明。截图 `runs/validation/quality-passed-browser-20260929.png` 已查看，日志完整换行可读。页面同时区分frame_limit达限与执行completed；未点击采集/归档/删除，不新增传感器数据。该证据只覆盖正常质量报告显示，不覆盖新增invalid_ego_pose错误协议的正式服务部署与页面验收。

- 正式质量任务HTTP正常路径验收：确认datasets/jobs全部空闲、两帧录制capture-20260929T161825-9e1187fd原状态not_checked后，POST /datasets/quality返回running，随后GET返回passed/returncode0；2同步样本、sensor_input RGB、米制深度、XYZI、BEV和14/14外参通过。报告manifest_sha256=738f4588f55fac63f829cea5de867ddf21ebae856921fa4f3beb739e5b92a29e，started_at=1790673485.0998948、finished_at=1790673485.3153102。独立validator读取当前代码；常驻audit_capture仍旧版（返回无problem_frame），因此不声明结构化位姿失败HTTP链路已部署。未重启仿真、未新增录制，仅保存正常质量报告；浏览器展示仍未验收。

- 质量原因协议边界验收：新增布尔/负数/小数/字符串/空值/超JS安全整数帧号拒绝、成功返回码携带失败协议不采用、重复协议行与多余字段不采用，全部退回一般失败且problem_frame为空。前端解析同步测试相同边界及旧报告无字段兼容。质量/数据/回放专项45 passed，两项Node报告/文案专项通过，diff检查通过；本轮不改生产逻辑，不新增录制，不等同浏览器验收。

- 位姿质量失败前端明确提示：validator输出严格invalid_ego_pose/frame协议，audit_capture仅在失败返回码且唯一合法协议行时采用原因和安全整数问题帧；不从异常文字猜测。报告解析校验problem_frame，页面现有告警区显示“自车位姿无效（帧N），不能用于可靠轨迹回放或评测”，保留详细日志和未自动修复说明。真实隔离validator→audit_capture测试确认frame42，质量/数据专项19 passed、Node文案及TypeScript通过。尚未实际浏览器验收；旧报告无结构化原因仍显示日志，不回写历史报告。

- S4/S5质量验收统一位姿规则：将刚体检查抽到data_quality.validate_ego_pose，回放与原始数据验收共享；validator对无效位姿返回包含具体frame的失败，现有质量报告detail可显示。隔离真实validator子进程验证frame42损坏位姿失败且无PASS输出，缺失/畸形矩阵与回放专项合计36 passed。已有两帧真实录制完整原始验收仍PASS、14/14外参通过；未新增录制或改原数据。未实际点击网页质量检查，不把测试等同页面验收。

- S5真实录制全帧位姿回归通过：对两帧上限录制capture-20260929T161825-9e1187fd全部2帧、DriveAdapter录制capture-20260915T204506-23771c1a全部80帧、规则基线capture-20260908T161417-253a8410全部400帧逐帧调用当前replay_trajectory（默认5秒窗口），共482次返回正确frame且interpolated=false，无刚体误拒。DriveAdapter其中49帧空间预测available，其余无预测不伪造；不证明预测时间或驾驶质量。三组耗时0.054/1.023/9.103秒，前后SHA256核对manifest/index及每帧JSON共488个文件未变化。不读写传感器原图、不新增录制、不重启服务；正式桥接部署及网页故障展示仍未验收。

- S5真值轨迹位姿校验：原实现只检查4×4/有限值，可把缩放、剪切、反射及非齐次矩阵当成真实自车位姿。现对当前、历史、未来全部选中样本检查刚体旋转正交性、行列式+1、齐次末行，不自动修复或改写原始录制。15种位置×损坏矩阵测试均拒绝且源文件不变，正常平移/旋转参考点测试保留通过；轨迹/预测专项58 passed。未重载桥接或进行页面异常展示验收，不改变预测时间契约、不启用ADE/FDE。

- 本机Blender锁继承实测通过：`python3 tools/verify_blender_restart_lock.py` 调用实际 `/snap/bin/blender` 5.2.2 LTS（d13f752e3b9c）。父侧关闭共享锁描述符后，Blender内os.fstat成功并等待stdin；外侧排他锁被拒绝；发送结束输入、Blender退出0后排他锁成功。临时目录自动清理，无生成资产、无Unreal调用、未碰运行中的CARLA。该证据替代“Blender是否主动关闭描述符未验证”的旧限制，但不证明真实资产导出中断/超时所有路径，也不解决旧桥接首次部署和导入历史核验。

- Blender生成子进程继承重启共享锁：通过pass_fds传递同一锁描述符，协调调用异常退出并关闭自身描述符后，存活子进程仍阻止排他重启锁。新增真实Python子进程持锁测试：协调调用抛错、子进程仍存活时排他锁失败；关闭子进程stdin、确认退出0后才可取得排他锁。相关专项131 passed。测试子进程不是Blender本体，不证明Blender不会主动关闭继承描述符；Unreal沿用其已有import.lock继承机制，正式服务未部署。

- Blender任务与桥接重启共用文件锁：生成/导入全调用持共享bridge-restart.lock；维护脚本从状态检查前至旧桥接退出持排他锁，并在启动替代桥接前关闭描述符。真实子进程运行复制维护脚本验证资产持锁时拒绝、释放后stop可结束；反向排他锁验证两资产入口不创建任务或调用外部进程。输入规范化保留在创建锁目录之前；资产/重启/自然语言计划专项130 passed，shell语法与diff检查通过。本锁只覆盖采用新代码的Blender入口，不涵盖其他仿真/数据入口，不是整个服务的原子维护协议；旧桥接未部署，不受新锁保护，尚不能直接按新脚本完成首次重载。进程意外退出后的子进程存活仍须结合既有日志/import锁核查。

- 最新完整后端回归：1716 passed，57.49秒，覆盖截至本次的资产生命周期、重启保护和桥接改动，取代1663项旧计数。导入日志新增四分支持久化故障测试：launching写失败不启动外部进程；exited写失败且错误回执成功时保留退出证据；错误回执也失败时保留preparing/importing不确定状态，不注册资产、不误报成功。外部进程为测试替身，临时日志真实落盘；不属于Unreal实机磁盘故障测试。正式服务部署、旧6条导入记录核验及重启竞态仍未完成，八阶段不标完成。

- 导入进程生命周期持久化：新增worker_state=not_started/launching/exited，外部进程调用前持久launching，返回后持久退出码；needs_attention且有明确未启动/已退出证据才归入settled_import_failures，不改变资产失败状态。旧6条日志虽均显示重名拒绝，但缺生命周期字段，继续保持未知、不按文本自动放行。真实临时日志覆盖缺字段、启动不明、矛盾目标、无返回码和布尔返回码拒绝；既有最终回执写盘失败+重复导入测试确认第二次未启动且不再阻塞重启。资产/重启专项111 passed。未部署、未新增原生导入；旧日志迁移与检查后新任务进入竞态仍未解决。

- 重启检查语义修正：实际全日志核查发现7条历史needs_attention；生成14425a5ddee5已有subprocess.run返回码0和有效结束时间，但manifest缺失，属于导出失败而非仍在执行。仅对这种有明确worker退出证据的生成失败，重启状态单列settled_generation_failures、不再阻塞；原日志仍needs_attention，未修复资产、不允许自动重试。无返回码、布尔/字符串返回码、无效或早于开始的结束时间仍拒绝；不将该规则套用到导入日志。专项104 passed，实际只读状态保留6条未解决导入。正式服务未重载，首次部署和剩余导入状态审查仍待完成。

- 资产重启状态隔离真实HTTP验收：使用生产 Handler、真实 BlenderPipeline 和临时持久日志，在随机本地端口覆盖生成/导入各自的空记录、执行中、needs_attention、终态及损坏记录，共10种情况；正常返回200，损坏返回400，实际 restart_guard 拒绝执行中/未知/待检查，日志字节保持不变。桥接、资产、普通及崩溃重启保护合计368 passed（11.86秒）。这是隔离HTTP验证，不是运行中正式服务部署，不调用 Blender/Unreal/CARLA，不证明终态资产实际存在或检查至重启之间无竞态。

- S1/S6 重启保护增量：新增只读 `/blender/restart-status`，扫描全部生成/导入日志（不受网页100条历史上限影响）；重启检查在普通、崩溃后及恢复模式均拒绝未解决资产任务和未知状态。历史 needs_attention 不自动视为已结束，不修改日志或杀进程。新增102份真实临时日志测试证明旧记录不漏查且原文件不变，损坏日志拒绝；重启/Blender/崩溃保护专项101 passed。本增量尚未重载、未做真实HTTP验收；旧服务缺新端点时脚本会拒绝，首次部署需检查全部资产任务后进行受控迁移。该快照检查尚不消除检查后新任务进入的竞态，不能声称完整重启事务已完成。

- 模型/规则录制前移检查：run/rule-run 明确 unified_capture=true 时也在启动前拒绝无效配额，防止子进程先启动后 collection_request 才失败；false 保持非录制评测可用。四分支测试及桥接完整专项257 passed。preset/live传感器不等于录制，未盲目阻止这些入口；本增量尚未重载实测。

- 隔离真实HTTP配额拒绝测试通过：随机127.0.0.1端口运行生产Handler/start_e2e代码，测试进程配置invalid配额，POST /collection/start 返回400/ok=false及准确配置错误，模拟器/执行状态访问替身调用数0。配置仅属于测试进程，正式桥接与CARLA未修改。相关invalid_quota筛选7 passed；不是生产服务配置故障或原生清理验收。

- 正常桥接重启实机验收：空闲和无未完成资产任务核对后运行 scripts/restart_studio_bridge.sh，精确进程身份及重启门禁通过，新PID1242030、PID文件由脚本更新。最近两帧采集会话保持completed，预检ready=true，CARLA episode4255126830586310679/Town04未变，异步且0传感器。最新采集配额启动/开关校验及错误分类已加载；未通过修改生产配置制造配额故障，所以该故障的真实HTTP验收仍未完成。

- 运行中开启录制也校验配额配置：配置无效时不覆盖原 collection-request.json；关闭录制仍可下发，不因配额异常堵住停止入口。真实临时文件测试覆盖开启拒绝/关闭成功，桥接专项252 passed。尚未重载本增量，不声明真实页面开关验收完成。

- S4 启动前校验增量：独立采集 recording=true 时，桥接在接触模拟器/创建执行前解析配额配置，无效立即拒绝；recording=false 的仅观察会话不受该配额配置阻挡。四种无效配置及非录制分支测试通过。仅前移配置有效性检查，运行时目录扫描/写入保护仍保留，不保证空间足够；桥接尚未重载该增量。

- 配额错误跨模块专项：在隔离测试环境使用真实 capture_quota_policy 解析五种无效配置，调用实际 SensorCapture._write_sample 并持有真实目录写锁，验证不创建 samples、保留 quota_unknown/saved_limit，实际 capture_failure 读取回执后分类为 capture_quota_unknown。采集故障和资源专项45 passed。manifest 回调及 worker 回执构造仍为测试替身，不能当作完整原生进程/HTTP故障验收；未修改服务环境配置。

- 当前完整回归更新：后端 **1663 passed，51.80 秒**；全部 tools/test_*.mjs、TypeScript、生产构建通过，构建保留 vinext Unknown 路由分类警告。取代下文1603等旧计数。覆盖当前代码自动测试，不替代未完成的长路线、多模型压力、配额故障实机、跨工具恢复和跨机交付；八阶段均不标全部完成。

- S4/S5 回放提示修正：历史 manifest 的 saved_limit+quota_unknown 不再解释成已达到容量上限，明确为配额无法确认的保护性停止，要求核对配置、目录可读性和数据质量；错误保存状态继续优先显示异常结束。Node 文案分支及 TypeScript 通过，未改写历史数据，浏览器故障记录展示尚待验收。

- S4 配额未知错误归因：execution_id 精确匹配的 sensor-rig 报告里 quota_unknown 映射为 capture_quota_unknown，其他未知原因保留 capture_worker；不从错误文本猜测分类，旧执行报告不归因给新任务。新增结构化标记、异常类型及执行身份测试；此桥接导入模块修改尚未重载，真实配置故障仍待验收。

- S4 修复未知配额误报正常完成：独立采集仅 frame_limit/storage_limit/disk_reserve/capture_quota 作为明确达限结束；quota_unknown 或未知 stop_reason 抛出失败并保留原错误、已录数量及清理结果，避免配额无法测量仍 completed。受控资源矩阵加入已知配额和未知停止分支；尚未执行真实配置故障测试，不改旧数据状态。

- 上述两帧录制追加原始质量校验：validate_capture_dataset.py 对 capture-20260929T161825-9e1187fd 返回 PASS，2 同步样本、sensor_input.npz RGB对应、米制深度、XYZI、BEV及14/14外参通过，目录约30MiB。采集上限验收脚本新增 audit_capture，今后须原始质量 passed 才写成功回执。此次未重录；校验不证明驾驶安全、语义BEV真值或所有模型输入契约。

- S4 两帧上限实机验收通过：执行97a33b6384234bbf9802679a038ee0da，录制capture-20260929T161825-9e1187fd，计划100步、实际3步保存2帧后 frame_limit 正常 completed，manifest saved_limit、索引2帧、cleanup_errors=[]。原生查询异步、0传感器、0采集车辆，Town04未切图。收据 runs/validation/capture-limit-b9fc061018b74a309a90a67cbfdbb94e.json。新增两帧测试数据保留；不是长录制、磁盘耗尽或完整数据质量验收，API dirty版本警告保留。

- S4 达限退出验证：检查独立采集主循环已有 stop_reason 后退出逻辑；新增 frame_limit/storage_limit/disk_reserve 三种受控分支，确认只处理首帧后结束（正常无上限分支处理10帧），回执保留原因/已录帧数，关闭采集后删除车辆并恢复设置。资源专项16 passed；属于受控对象测试，未制造真实20GiB录制或磁盘不足。

- S4 采集容量提示：核对独立采集固定 max_frames=2000、SensorCapture 20 GiB 单次容量及磁盘余量保护，启动区现在按时长/采样间隔提示采样机会与超帧数边界，明确可能提前停止，不承诺全程录制。Node 边界测试与 TypeScript 通过；未新建录制，仍不代表全 runtime 配额已实现。

- 重启脚本真实进程拒绝专项：临时目录运行无关 Python 子进程，命令参数故意包含 tools/livery_bridge.py；复制生产脚本执行 --stop / --after-crash-stop / --resume-recovery，均在身份检查阶段拒绝，子进程继续存活并最终正常退出，不创建桥接日志。restart_guard 18 passed。未操作正在运行的桥接/CARLA；正常重启路径和 PID 检查至信号之间的竞态仍非该测试覆盖范围。

- 服务恢复后管理记录修正：旧 bridge.pid=171087、carla.pid=10932 已过期；精确命令行/cwd、PID start_ticks 与空闲检查通过后，更新为桥接1217689、CARLA1219324。未停止服务。桥接重启脚本由部分字符串匹配改为精确 argv 校验，脚本语法及既有 restart_guard 15 项通过；该测试集不等于实际重启或新 shell 分支的完整验收。

- 网页 failed 状态已核查：会话 6ae8e07391e74a34a83be9399b84998d 是既有采集写锁冲突注入，错误 Another capture writer holds admission lock，分类 capture_io_error。当前真实预检 ready=true，session_idle/map_handoff/CARLA 等检查通过，Town04 异步。页面改为分别显示“最近预检”和“最近会话”，提示这是查询快照，保留失败日志；TypeScript 通过。本次未重新运行模型，不外推为完整健康验收。

- 最新全量后端回归更新为 **1603 passed，50.02 秒**，涵盖当前 Blender 导出完整性、只读协调进程观测及独立进程中断测试。替代下文 1555 项旧记录，不替代实际引擎崩溃、网页和长路线验收。

- 本次重新盘点：录制 222 → 221 份，分配占用 89.776844 → 88.786873 GiB，减少约 0.990 GiB。runtime 清理前约 102 GiB。
- 实际删除 `capture-20260914T122421-791fd035`：已结束、无本地派生/项目/队列/数据划分引用的一秒中间调试录制。保留 400 帧规则采集基线及所有执行/结果日志；这不是逐字节等价替代。旧原始传感器文件不可恢复。
- 全部 JSON 元数据和哈希清单：`runs/validation/short-capture-cleanup-bdd6cf3c277a4323bc5bbce2518292d0/`。清理持有采集写锁和划分注册锁，前后核对身份、空闲状态和保留标记。
- 此前两份重复恢复副本清理约 132.36 MiB，属于历史执行，不重复计入本次 0.990 GiB。
- 未清空其余目录：模型/切图/取消/故障恢复基线、项目引用、队列引用以及来源录制继续保留。未标记不等于无用；剩余不是全部垃圾。
- S2/S3：代表车辆和行人的材质撤销重做、只读诊断和明确恢复已完成真实接口验证；行人网页正常操作与受控失败恢复已验证。不是所有对象覆盖，也不是实际引擎崩溃恢复验收。
- S4：采集写锁冲突错误归因及零样本恢复拒绝已部署并经真实 HTTP 验证，取代下表“尚未部署”的旧描述。
- 最近完整后端记录为 1555 passed；之后新增功能只有相关专项验证（最近 actor/环境历史 36 passed），不能宣称当前全部新增代码全量通过。生产构建通过，保留 Unknown 路由警告。
- 后续顺序：S1 多模型长任务/异常恢复；S4/S5 数据契约、长录制和回放；S6 跨工具失败状态与回滚；再补齐任意资产、批量矩阵和跨机交付。GitHub 最新提交推送仍未完成。

| 阶段 | 已实现及已有验证 | 仍未完成 |
|---|---|---|
| S1 稳定性 | 会话独占、预检、停止清理；VAD/TCP/ADMLP/UniAD 短闭环，TCP 单路线完成 | 多模型长路线、压力及完整崩溃恢复；TCP 有碰撞，不是安全驾驶通过 |
| S2 场景编辑持久化 | 来源区分、稳定 ID、版本保存恢复、复制撤销重做、环境材质历史与受控失败恢复 | 跨操作统一撤销顺序、所有入口纳管、完整补偿和网页故障验收 |
| S3 精准纹理 | 代表车辆/行人/建筑/道路/道具真实网格、UV、材质槽与实景验证 | 任意资产覆盖、完整预览与实景一致性验收 |
| S4 数据采集 | 六路辅助 RGB、深度、点云、标定、真实模型输入、质量校验、配额锁、恢复副本 | 全 runtime 配额和清理事务、长录制；最近恢复状态及采集错误分类尚未部署验收 |
| S5 回放诊断 | 多视角、深度/点云、轨迹、片段、ROS 布局、离线播放 | 预测时间契约、可靠 ADE/FDE、TF 几何与吞吐验收 |
| S6 自然语言资产 | 结构化计划、确认执行、基础 Blender→Unreal→Blueprint→CARLA | 复杂资产、跨工具回滚；任意道路地图生成尚不支持 |
| S7 批量实验 | 队列、重试、配置追溯、纹理 A/B、比较账本 | 完整场景×模型×天气×纹理矩阵与长任务故障验收 |
| S8 迁移交付 | 项目资产包、路径检查、同机隔离恢复、严格源码导出 | 最新提交推送、跨机依赖和引擎重建验收 |

本轮最新完整后端回归为 **1536 passed，49.54 秒**，更新此前 1526 项记录。恢复响应 Node 专项与 TypeScript 检查通过；没有重跑全部前端专项或生产构建。测试通过不等于全部功能完成。

后续前端验证更新：全部 `tools/test_*.mjs` 执行通过，包含新增恢复请求超时/中止契约；生产构建也已在上一轮通过（保留 Unknown 路由分类警告）。后端新增零样本测试后只重跑恢复专项 35 项，不将 1536 项旧全量结果当作新增测试已全量执行的证据。

## 采集失败归因实机增量验收

S2/S3 显式恢复并发/写盘异常专项补齐：同实例双线程恢复仅一次原生调用，另一请求拒绝；恢复意图写入失败时不调用原生修改，最终回执失败时保留 needs_attention，最终与错误回执均失败时保留 attempting。所有分支保留原操作 state/pending；已有不确定恢复回执即使重新检查得到新 token 也不直接重试。actor/环境历史专项 36 passed；属于隔离线程与持久化故障注入，不是多浏览器、跨进程或磁盘耗尽实测。未修改运行中场景。

S2/S3 网页 actor 显式恢复通过：临时行人 1236 的受控失败记录 eb28fe8ed468464585d233044025dd7f，经页面实际点击只读检查→选择操作起点→勾选确认→执行明确恢复；重新检查显示无覆盖、原失败保留和恢复 confirmed，不再提供恢复表单。持久日志仍 needs_attention，recovery.desired=null；provenance 覆盖为空。截图 `runs/validation/actor-history-browser-b3c05261dbc7441dae7184375c5dc7d9/recovered.png` 已查看，显示的是回执/登记，不是实景截图。身份核对后删除临时行人，新 tick 无残留、idle/ready 通过。fixture 是真实应用后受控回调/回滚失败，不是引擎崩溃；网页恢复异常网络、多标签竞争仍待验收。

S2/S3 车辆受控异常恢复实机验证通过：`runs/validation/duplicate-texture-fc2b25208ec843e0be703612cf9a2f22/report.json`。Audi A2 真实应用后注入回调/回滚失败，再经新检查凭据明确恢复 source；保留原失败记录、恢复回执 confirmed、登记覆盖移除、重复恢复 400。recovery-before/after.jpg 已查看，白色测试 atlas 与彩色标记恢复为原红色车漆；不是逐像素隔离验收。新客户端/新 tick 独立确认本轮及上轮行人测试 actor 1218/1224/1227/1233 全部不存在，idle/ready 通过，未切图。此为受控调用失败，真实引擎崩溃与网页显式恢复仍未验收。

S2/S3 actor 显式恢复已部署，行人受控实机验证通过：`regression_duplicate_texture.py --material-history --material-recovery --pedestrian` 在临时行人真实 HTTP 应用确认后注入调用异常及回滚异常，生成 needs_attention，再经检查 token 明确恢复 source。原失败 state/error 保留，恢复回执 confirmed、登记覆盖为空，同请求再次恢复 HTTP 400。收据 `runs/validation/duplicate-texture-df820266da254b6db39491c98a57ef7f/report.json`；recovery-before/after.jpg 已查看，棋盘裤装恢复为原深色裤装。测试结束恢复原期望纹理继续复制检查，并清理临时对象/恢复相机，报告 passed。未切图；这是受控回调/回滚失败，不是真实 CARLA/桥接崩溃或磁盘故障。车辆恢复与网页明确恢复仍待验收。

S2/S3 actor 异常恢复接口/页面接线：新增 actor-history-recover 路由；actor 检查响应明确声明 actor_recovery_supported 后，页面才提供最新 token 对应的目标选择与确认。actor 请求发往专属接口，保留超时/响应身份校验与不自动重试；已存在恢复回执时不再次开放恢复。旧服务缺能力仍只读。Node 解析/路由专项与 TypeScript 通过，补充桥接明确确认与原生世界忙时拒绝测试。尚未部署、未做真实 HTTP 故障恢复或网页恢复验收，不能将接线完成当作功能验收通过。

S2/S3 actor 异常显式恢复后端增量：复用持久恢复协议和独立回执验证，基于最新检查 token 与用户选择 source/target，保留原 state/pending/error，已有恢复回执禁止再次提交。测试覆盖两种目标、旧 token、登记变化、恢复调用失败，共 32 项 actor/环境历史测试通过。桥接抽取共享精确身份/登记验证回调，新增要求空闲世界与明确确认的恢复动作函数；原身份矩阵 16 项通过。尚未接 HTTP 路由和网页、未部署实测，不能宣称异常恢复可用。

S2/S3 actor 只读诊断已部署并完成真实 HTTP 三态测试：walker.pedestrian.0001 收据 `runs/validation/duplicate-texture-ba7b561e92fd4dda8571726b43c80e07/report.json`，Audi A2 收据 `duplicate-texture-085173ab2d724fadb7af970385acca23/report.json`。应用/撤销/重做后查询分别与 target/source/target 一致，对象身份精确匹配，每次查询前后日志字节保持；native_verified=false、automatic_retry_allowed=false。两轮通过，未切图，脚本清理对象并恢复相机。真实网页诊断显示及异常记录实机诊断仍待验收，不把正常三态检查外推为故障恢复。

S2/S3 actor 只读诊断页面已接代码：历史记录调用 actor-history-inspection 专属端点，校验支持蓝图、组件槽、episode、运行时 ID 和稳定 ID字段，显示登记引用与起点/目标比较。复用显示组件但显式禁用 actor 恢复按钮，拒绝未支持的恢复回执，避免将环境材质恢复接口用于 actor。Node 专项与 TypeScript、差异检查通过；新诊断接口尚未重载部署，真实网页诊断响应未验收。比较只涉及登记表，不声称 GPU 状态或自动修复。

S2/S3 actor 异常材质只读诊断新增代码：`/materials/actor-history-inspection` 核对当前 episode/actor/蓝图/稳定 ID/用户来源，比较当前登记纹理与操作起点/目标（pending 时使用未完成转换两端），返回 source/target/neither 与 native_verified=false、automatic_retry_allowed=false。检查不写日志、不解除 needs_attention；新增三种引用匹配及桥接身份拒绝矩阵测试。尚未部署、未接网页诊断入口，不声称能读取 GPU 状态或自动恢复异常。

最新完整回归更新：**1555 passed，49.96 秒**；全部 Node 专项和 TypeScript 通过。该结果更新下方历史 1536 项记录，但不替代缺失的网页、长路线、故障和跨机验收；八阶段仍未全部完成。

S2/S3 actor 纹理转换异常专项：新增同一 ActorMaterialHistory 实例双线程同时撤销测试，只有一次 apply、一条 transition，另一个请求版本不符拒绝。新增写入意图失败、最终提交失败、提交与错误回执均失败三种持久化注入：分别不执行原生修改、保留 needs_attention、保留 attempting，后两者不能直接重试。actor 模块 9 项通过；全部 Node 专项、TypeScript、差异检查通过。测试范围是隔离线程/写盘模拟，不是跨进程服务、真实磁盘耗尽或原生崩溃验收。

S2/S3 纹理撤销实景三态补验：脚本 --material-history 新增同一观察相机下 material-applied/undone/redone.jpg。行人收据目录 `runs/validation/duplicate-texture-34101a3718d84393ba95a7677e2d04a2/`，车辆目录 `duplicate-texture-6c41bdff56864760afe0791a21230b16/`，两轮 passed，六张三态截图均已查看：行人裤装棋盘→原深色裤装→棋盘；车辆彩色局部覆盖→原车漆→彩色覆盖。截图存在自然画面变化，不是逐像素或所有材质槽隔离证明。测试报告清理对象、相机恢复成功，未切图；本轮未追加独立世界快照清理复核。车辆正常网页按钮验收及故障矩阵仍待完成。

S2/S3 活行人网页纹理撤销重做验收：临时 actor 1189，操作 246dc554c0bb4eff9855425a22e7972b，浏览器实际勾选撤销再勾选重做，页面依次显示已撤销/操作已确认。磁盘核对 transitions=[undo,redo]、目标 null→原哈希、provenance 纹理恢复。截图 `runs/validation/actor-history-browser-2d28ed46e36d437a82e6ec129ec60231/undone.png`、`redone.png` 已查看，证明网页状态而非实景逐像素变化。身份核对后删除临时对象，删除接口成功并保存自动快照；即时旧客户端 get_actor 检查曾失败，后续使用新客户端/新 tick 独立核对，无重复删除。未切图。车辆正常网页流程、视觉前后比较及故障矩阵仍待完成。

S2/S3 网页能力已部署并验证旧对象拒绝路径：空闲身份核对后重载桥接，浏览器打开统一历史，显示车辆/行人精确槽与确认撤销按钮。对已删除 actor 1184 的历史 a694c1fd1ab641819d1c802c2196d86c 实际确认提交，返回 Actor material identity changed，页面锁定直接重复提交。磁盘日志仍 confirmed、原两次 transitions、无 pending；截图 `runs/validation/actor-material-browser-stale-rejection-20260929.png` 已查看。此为真实网页拒绝验收，不是仍存活对象的网页正常撤销重做验收；未创建对象、未切图。

S2/S3 actor 纹理网页操作已接代码：历史响应新增独立 capabilities.actor_material_transition，保留旧日志 undo_supported=false 原样；页面仅在服务明确声明能力且记录 confirmed/undone 时提供确认后的撤销/重做，发送到 actor 专属接口、携带 revision，待检查记录不提供按钮。旧服务缺能力字段仍只读。能力布尔值、缺失默认、状态解析专项及 10 项历史测试、TypeScript 通过。能力响应尚未重载桥接，页面真实按钮未验收；能力声明仅表示接口存在，不证明当前对象仍符合执行条件。

S2/S3 actor 纹理撤销重做接口已部署，代表真实 HTTP 验证通过：Audi A2 和 walker.pedestrian.0001 应用→撤销→重做，登记覆盖移除后恢复，旧 revision 返回 400；带纹理复制撤销重做也通过。收据 `runs/validation/duplicate-texture-a454e11dd6864759a454d905976f5e48/report.json`、`duplicate-texture-a0724cc927394993826b67f9fad2c27f/report.json`。脚本报告对象清理和相机恢复成功；随后独立世界快照检查因自动审批服务断流而未执行，不能宣称已独立复核。未切图，未保存撤销中间态截图，未验收页面按钮或真实故障矩阵。旧 undo_supported=false 标记仍对应只读页面，开放按钮前需统一能力字段。

S2/S3 actor 材质历史 HTTP 路由已接代码：`/materials/actor-history` 返回操作 ID、新 revision、applied 与完整回执；测试矩阵覆盖正常撤销以及 episode、对象缺失、蓝图、稳定 ID、来源、登记纹理变化和活动评测拒绝，拒绝前不写 pending、不调用原生修改。相关后端 233 项通过。页面解析同步识别 undone/pending，防止撤销后仍显示操作确认；Node 专项和 TypeScript 通过。尚未部署该接口、未实机调用、没有页面撤销按钮；现有 undo_supported=false 表示页面未开放，不作为接口可执行性证明。

S2/S3 actor 纹理撤销重做后端增量（未开放）：复用环境材质的持久转换协议，actor 专属读取器增加 revision/applied/pending/transitions 验证；正常撤销重做、旧 revision 拒绝、原生失败待检查和禁止重复执行测试通过。桥接新增动作函数校验当前 episode、运行时 actor、用户来源、稳定 ID、蓝图及登记纹理，再准备精确槽事务；尚未接 HTTP 路由/网页，未部署实测，因此日志仍标只读。历史模块专项 30 项通过，桥接现有专项通过不等于新动作函数身份矩阵已验收。

S2/S3 actor 材质日志已部署并实机验证：空闲及进程身份核对后重载桥接，运行 duplicate_texture --redo 与 --redo --pedestrian。应用响应 history_operation_id 对应统一历史 confirmed/actor-material，稳定 ID、运行时 actor、蓝图、before=null/after 哈希准确，undo_supported=false。带纹理副本复制撤销重做保持原源和副本材质。证据分别为 `runs/validation/duplicate-texture-9909af96a693426eaeaec28efc977aac/`、`duplicate-texture-810be8e3afba49d1aede6f65566df465/`；已查看两张 duplicate.jpg，车辆后轮拱彩色标记与行人裤装棋盘可见，未做逐像素比较。独立世界查询确认测试 actor 1169/1170/1171/1174/1175/1176 均不存在，idle/ready 通过，相机由测试恢复。未切图。此轮验证真实接口日志，不冒充历史网页验收或 actor 材质撤销实现；API/模拟器版本差异警告保留。

S2/S3 actor 纹理日志接统一历史：新增有界、身份/槽/哈希/状态校验的读取器，聚合接口纳入 actor-material 并对损坏项给出不完整警告；页面独立展示稳定 ID、蓝图、组件槽、前后引用，明确只读，不复用环境材质撤销与恢复按钮。初轮相关后端 233 项与 TypeScript 通过；补充真实日志聚合/损坏项不改源及前端不误用环境材质操作测试。尚未部署、未实机生成日志或网页验收，撤销重做仍未实现。

S2/S3 受管 actor 纹理写前日志新增：apply_versioned_livery 接入独立 actor-material-history，覆盖 Audi A2 槽 4 与 walker.pedestrian.0001 槽 14，保存 episode/actor ID/stable ID/蓝图/组件/槽及前后哈希。先持久化 attempting 再调用事务，原生失败尝试既有回滚并记录结果、保留 needs_attention；成功回执落盘失败保留 attempting，明确结果未知。日志不声明 GPU 状态，也没有提供撤销接口。初轮模块及桥接测试 222 passed，补充初始/最终写盘失败后模块 4 passed，差异检查通过。尚未重载桥接、未实机验收、未接统一历史网页；非受管及其他旧纹理入口仍未覆盖，S2/S3 不标完成。

零样本拒绝修复已部署并完成真实 HTTP 验收：空闲及 PID/cwd/cmdline 核对后仅重载桥接，`regression_empty_capture_recovery.py` 使用现有零样本录制，确认 failed 与明确中文原因、没有 candidate/recovered ID、专属暂存目录为空、源文件清单和哈希保持；同请求再提交仍为原 failed，不启动新副本，结束 idle/预检通过。收据 `runs/validation/empty-recovery-2ab8914c231b47619203aab2b19af449.json`。未切图、未新增传感器数据、未删除数据；这次是 HTTP 验收，新文案的浏览器截图仍未补录。

浏览器实际提交零样本故障录制恢复：`capture-20260929T141403-17dd8aed` → 请求 `2ad47b04786344a180af8227d61de4d2`，页面显示 failed/copying、请求专属暂存位置，无成功回放按钮。截图 `runs/validation/recovery-zero-samples-browser-20260929.png` 已查看。发现错误文案暴露底层 samples 目录不存在，已在 recover_capture 加入明确“没有已提交样本可恢复”拒绝，并测试不改源、不创建副本；35 项恢复测试通过。该文案改动尚未重载桥接，截图记录的是修复前信息，不冒充修复后验收。前端生产构建通过，保留 vinext 路由 Unknown 警告；未进行浏览器断网/丢响应测试。

恢复写请求生命周期增量：页面调用独立 requestCaptureRecovery，将 HTTP 等待及 JSON 读取共同置于有界超时；卸载/切换录制中止客户端等待，旧响应不能回写当前 job/error/pending。客户端中止不意味着服务器取消，原请求 ID 仍保留用于幂等查询。专项注入网络失败、HTTP 失败、身份不符、响应头/响应体挂起、外部中止和启动前已中止，验证没有自动重试；测试与 TypeScript、差异检查通过。首次类型检查发现 .ts 导入扩展名不兼容项目设置，已改为扩展名省略，测试通过 Node 类型剥离加载同一生产源。尚未做浏览器级切换/断网测试；此项不宣称该层验收完成。

恢复页面未知结果处理增量：checking 状态允许用户重新明确确认后提交同一请求 ID，依赖后端已有幂等协议返回原任务或启动原请求，不自动重试、不生成第二个 ID；running/needs_attention/recovered 禁止重新提交。写请求 pending 期间停止读轮询，结束后恢复查询。新增 ID 选择单元测试，涵盖未知状态原 ID、ID 错配拒绝、阻止运行/中断/完成态提交、失败态新请求；Node 专项、TypeScript 和差异检查通过，恢复服务专项 16 项通过。尚未进行浏览器丢响应/断网整体实测，不将单元测试当作该场景验收。

桥接已加载最新错误归因逻辑。受控根写锁冲突测试 `runs/validation/capture-lock-8c3d0fe006bb4fdd8bf66a78a034e805.json` 通过：执行 `6ae8e07391e74a34a83be9399b84998d` 明确 failed，failure_category=capture_io_error，会话显示 Another capture writer holds admission lock；worker execution_id 匹配，记录数 0、cleanup_errors=[]。录制 `capture-20260929T141403-17dd8aed` 为 saved_capture_error，索引为空；结束后无传感器/采集车辆，世界异步，idle 与预检通过。未切图或重启 CARLA。这不是实际磁盘耗尽或完整崩溃矩阵验证，保留 API 与模拟器 dirty 版本差异警告。

错误归因、恢复服务及配额专项 51 passed；恢复响应 Node 专项与 TypeScript 检查通过。测试产生了一份零样本故障记录，不能把之前清理后的 221 份当作持续不变的当前计数。

## 当前存储及清理结果

### 后续实际执行（取代下方首次受阻状态）

确认 8765 无监听、桥接进程不存在、持久会话 completed 且未发现采集 worker 后，启动桥接；未重启 CARLA 或切换地图。运行时空闲/后台任务/切图状态检查通过。

已删除两份重复恢复目录 `recovered-e0f80435373d4fdba83aac8d8d06bcb2`、`recovered-d591b839253244fa8f0c830491dfbb4c`。保留最新副本 `recovered-4f6835a9ab294e358ef6ad40d0d1c1d3` 及原源。样本、索引、标定和场景逐文件 SHA256 一致；恢复报告源文件清单和排除尾帧一致。历史报告因时间与副本身份不同而单独保留，没有忽略原始数据差异。

删除逻辑数据 138,786,156 字节（约 132.36 MiB），不是数十 GiB；原始样本仍在最新副本，旧副本全部 JSON 元数据和完整哈希清单保存在 `runs/validation/duplicate-recovery-cleanup-76ea82cad7f0461aae74974f0d1d097b/`。旧目录已删除，不再是可打开的数据集；历史文档中旧 ID 仅作为历史验收身份，回放使用上述替代副本。本操作不是对全部无用数据的清理完成声明。

复核盘点：`/tmp/safeagent-after-duplicate-cleanup.json`。

### 首次盘点与受阻记录

- `.runtime` 约 102 GiB；场景目录识别 223 份录制，分配空间 89.903458 GiB。
- 盘点：`/tmp/safeagent-current-cleanup-review.json`。本地引用扫描完成；7 项旧格式/暂存提示不是引用读取失败。
- 两份约 3 GiB 的大恢复副本是 ORIGINAL_MODEL_FAULT_RECOVERY.md 明确保留的模型故障恢复证据，不删除。
- 另找到同一源的三份五帧恢复副本。拟保留最新 `recovered-4f6835a9ab294e358ef6ad40d0d1c1d3` 和原源，只有逐文件一致、引用及空闲检查通过才清理两份旧副本；脚本默认为预览。
- 实际执行在第一步本地桥接空闲检查即遇到 Connection refused，尚未开始文件一致性审核或删除。**本次删除 0，释放 0。** 不把服务不可达当作系统空闲，也不重启服务来强行清理。
- 下一步恢复可验证的服务状态，重跑审计；大规模清理还需要逐组核实替代基线，不能按日期或未标记直接删。

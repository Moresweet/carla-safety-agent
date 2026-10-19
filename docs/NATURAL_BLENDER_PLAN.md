# 自然语言到本地 Blender 基本体

Asset Workshop 新增“自然语言→本地参数化Blender模型”。例如：

`生成一个蓝色长方体，长2米，宽40厘米，高0.8米，粗糙度0.6`

先编译保存计划、查看精确参数和限制，勾选确认后才生成。编译不启动Blender；
生成不会自动导入Unreal或生成CARLA对象，仍分别使用下方第2/3步。
生成成功同步手动表单参数及名称，避免显示的粗糙度等与刚导出的计划不一致。

当前支持长方体/立方体、圆柱体、圆锥体、球体、平面；蓝红黄绿白黑灰；
必须明确带米/厘米单位的长宽高，粗糙度0..1。省略颜色/粗糙度会展示默认值。
三轴为包围盒尺寸，不等轴圆体可能为椭球/椭圆截面；平面不产生实体厚度。
未知子句、重复字段、缺失尺寸或越界值整次拒绝，不用默认方块冒充复杂模型。
这是有界中文参数编译器，不是通用LLM、自由形状文本到3D服务，也不执行模型生成的脚本。

POST /blender/plan 仅接受description。计划保存在Blender任务根目录的plans目录，
SHA-256绑定实际文件字节；POST /blender/execute-plan只接受该SHA和confirmed=true。
执行前核验字节和支持的编译结果，不能附带参数偷偷改写计划。
生成报告关联plan_sha256，失败留存继承既有生成记录；修改描述必须重新编译/确认。
不承诺跨浏览器重复请求幂等或进程强杀后自动恢复。

## 验收

934项完整Python、TypeScript通过。首轮浏览器5b3f0ca0-3ec9-429b-a96a-e41283f253ca
生成任务da26fc63cf0b，计划SHA为5814dd032f4394c716162d39b1c45d04ecfaa7975fdaaef9aa12d72d3519f3e8。
随后真实导入报告asset-import-83b6eab2de164b29887de2a7e1076026：

- Unreal导入退出0、6项警告保留；唯一Blueprint为generated.prop.importaudit_def24558ffa44d3e。
- 同名再次导入拒绝，不覆盖旧资产；子进程继承导入锁。
- CARLA Actor1546生成并聚焦；已查看实景蓝色长方体图。
- 测试对象清理、相机恢复，同Town04 episode4224606802182015836，5秒异步推进、零传感器。

后续表单参数同步修正的最终GUI15147cb9-845f-424a-9ee7-c46926ebf52a再次真实导出通过，
已查看导出截图确认粗糙度0.60。该第二次导出没有再次导入Unreal。
源文件、已注册唯一资产和成功/同名拒绝报告保留，不自动删除。
# 导出完整性补验（2026-09-29）

完整重开链路实机补验通过：确认模拟器不存在后按原参数启动 Town04，可视化进程就绪，预检 ready=true。运行 regression_asset_import --job-id 0f92d5997ced --require-inherited-lock：重开→独立名称 ImportAudit_f91b590447084b61 导入退出0→注册matching→同名重复拒绝→临时 actor124生成/聚焦/截图。收据 `runs/validation/asset-import-0cf9fbd37c0a4e5c9aca515d9f12f8a6/report.json`，settled-preview.jpg 已查看，蓝色长方体可见。脚本结束删除临时对象、恢复相机，5秒异步观察0传感器，episode4255126830586310679；源与独立注册资产保留，不是资产回滚测试。启动保留缺失行人动画/分割材质警告与API dirty版本差异；本轮为HTTP完整链路，不冒充网页点击导入或复杂模型验收。

重开后导入实测尝试未启动：regression_asset_import --job-id 已改为调用真实重开接口并核对注册诊断。首次预检连接拒绝，确认原桥接执行句柄已结束143且8765无监听；恢复桥接后预检仍拒绝，具体为127.0.0.1:2000 CARLA transport unavailable，其余环境/磁盘/空闲/切图检查通过。没有执行导入或生成对象，没有新测试资产。需恢复模拟器后继续，不将此前网页重开通过扩展为完整链路通过。

真实网页重开验收通过：新浏览器 tab19 进入 Asset Workshop，展开 0f92d5997ced 并点击重开；工作台恢复任务 ID、名称、1 对象/8 顶点/1 材质和三种输出，第2步导入可用、第3步生成禁用。本轮未点击导入。截图 `runs/validation/reopen-asset-browser-20260929.png` 与 `reopen-asset-browser-actions-20260929.png` 已查看；发现说明截断，新增局部换行样式后截图 `reopen-asset-browser-actions-wrapped-20260929.png` 确认全文可见。历史产物参数未同步到编辑表单，页面明确说明表单不修改历史产物。页顶 session failed 仍存在，不将资产重开成功当作整体健康；需后续核查具体会话。

重开接口已部署并真实 HTTP 验收：身份/空闲/导入锁核对后仅重载桥接；真实任务 0f92d5997ced 重开 200，重复空 ID、额外空参、路径穿越、缺失任务均 400。六个原文件 SHA256 前后不变，结束空闲检查通过，未启动 Blender/Unreal 或切图。收据 `runs/validation/reopen-asset-d0f19be663384495b4ad8e3de24dbcb2.json`。网页按钮及重开后继续导入仍待验收；近期注册持久化/历史诊断代码随此次重载加载，但不因此声称所有新分支实机验证。

重开路由专项补验：直接执行生产 Handler.do_GET，覆盖合法请求、缺参、空值、重复 ID（含空重复值）、额外空参数、缺失任务和路径穿越输入，响应 200/400 与调用边界符合预期。修复 parse_qs 默认丢弃空值导致重复/额外空参数未被严格拒绝的问题。Blender/桥接专项 316 passed；使用隔离 Handler 和受控资产读取器，不等同真实 HTTP 或浏览器验收。

历史资产重开接线：GET /blender/exported 要求单个 job_id，返回经校验的已导出产物；生成历史 exported 条目增加重开按钮，工作台清除旧结果后只读加载，绑定响应 job 身份，不自动导入/生成，忙时禁用。提示表单参数不会修改历史产物。TypeScript 及 Blender/桥接现有专项 308 passed；新路由尚未重载、真实网页流程与路由专项尚待验证，不能把已有桥接测试通过视作新增路由覆盖。

刷新后继续工作增量（后端基础，未接网页）：exported_asset 只读重开已确认 exported 的精确任务，核对报告身份和三种非空、非链接输出；拒绝 generating/preparing/needs_attention，不把部分产物升级成功，不执行外部工具。真实任务 0f92d5997ced 只读重开通过，专项 86 passed。HTTP/页面选择历史资产尚未接入，因此尚不能宣称刷新后继续导入已完成。

前端历史解析补齐：校验列表上限、记录/任务 ID、重复 ID、按端点区分状态、有效时间、文本及可选诊断对象，损坏响应走刷新错误而不直接渲染对象；旧服务缺可选诊断字段仍可读。Node 无效记录专项与 TypeScript 通过；本地真实后端结果直接交给生产解析器，6 条生成、12 条导入均通过。此为文件读取到解析器的兼容验证，不是 HTTP/浏览器故障验收。

历史读取增量：本地真实记录只读核对为 7 条 registered/matching、5 条 needs_attention/absent。页面历史请求新增覆盖响应头和 JSON 体的 15 秒期限，卸载取消；挂起不再永久占住刷新标记。Node 端点/头体挂起/预取消测试通过，TypeScript 初轮发现 JSON unknown 类型后修正通过。尚未做浏览器断网实测，记录行字段的完整运行时解析仍需补齐。

注册只读诊断增量：导入历史以 attempt ID、资产名/Blueprint ID、目标网格路径及退出码核对当前注册表，返回 matching/absent/conflict/unknown；页面显示核对范围，不将匹配登记当作原生资产或场景验证，不改原失败状态、不自动重试。注册表损坏时历史仍可读并标 unknown。回执失败两分支确认 matching，身份/退出码/损坏矩阵验证原始日志和注册表字节不变。专项 83 passed、TypeScript 通过；尚未部署及网页验收。

注册后回执故障专项：注入注册表已持久化后最终成功回执失败，以及成功/错误回执均失败，分别保留 needs_attention/importing；已登记资产和 Unreal 结果不删除。再次同名导入在启动 Unreal 前拒绝，注册表字节不变。错误回执也无法保存时返回包含原操作报告路径的明确 RuntimeError。专项 77 passed；为隔离持久化故障注入，非真实磁盘耗尽/断电，尚未部署该增量。

导入持久性增量：历史读取校验文件名 attempt ID、job 目录、报告路径、有限时间戳、允许状态及非符号链接；现有 12 份真实记录通过只读兼容检查。Blueprint 注册表改用已有 durable_write（文件 fsync、原子替换、目录 fsync）。注册写入失败注入保留 needs_attention，不报注册成功；专项 75 passed。本增量未重载服务、未做真实断电测试，不能宣称跨工具事务完整。

部署更新：空闲、桥接 PID/cmdline/cwd、无桥接持有的未完成资产任务及导入锁检查通过后，仅重载桥接，未重启 CARLA 或切图。第一次启动因审批服务断流未执行，核查后经正常审批重试成功。真实 HTTP generations/imports 均可读，六条生成记录中包含 `0f92d5997ced` 的 exported，结束空闲检查通过。当前无 preparing/generating 记录，故本次不能证明新 observation 字段的 HTTP/网页分支；该分支仍只有隔离测试证据。运行桥接已加载近期修复，取代下文“尚未重载”历史描述。

独立进程中断增量验收：测试分别在生成/导入写入 generating/importing 后用 os._exit(37) 结束真实协调进程，随后重新读取历史两次，均识别 coordinator=exited、child_state=unknown、禁止自动重试；原日志字节保持，不创建注册表。外部工具调用由受控函数替代，因此不是 Blender/Unreal 子进程存活或引擎崩溃测试。相关专项 66 passed；当前完整后端回归 1603 passed（50.02 秒）。运行中桥接仍未重载，网页显示尚未实测。

后续增量：生成/导入历史现在只读观察协调进程 PID+start_ticks，返回 present/exited/unknown，并在页面提示已退出或无法确认。保持原持久状态不变，不把协调进程退出误当作 Blender/Unreal 子进程退出，也不自动重试。权限读取失败为 unknown；PID 重用为原协调进程退出。专项 64 passed、TypeScript 通过。尚未重载桥接和网页实测；子进程独立跟踪、显式恢复仍未完成。

修复 FBX 导出失败仍返回 ok=true、后端仅信任成功标记的问题。完整导出现在要求任务目录内固定 asset.blend、asset.glb、asset.fbx 均为非空常规文件，拒绝缺失、空文件、外部路径、符号链接及 null；失败记录 needs_attention，保留部分文件，不注册资产、不自动重试。

Blender pipeline / asset plan / package 专项 54 passed，新增三种格式各五种无效输出测试。真实本机 Blender 5.2.2 执行已保存蓝色长方体计划成功，任务 `0f92d5997ced`，三种文件均导出，回执 `.runtime/blender-assets/0f92d5997ced/generation.json`。本次未导入 Unreal、未生成 CARLA 对象、未切图，不能作为整条链路重新验收。运行中的桥接尚未重载；中断任务状态观测和跨工具恢复仍待实现。本检查证明文件存在与归属，不证明所有文件内容可导入。

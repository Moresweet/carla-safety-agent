# 两个剩余模型的原始输入契约

2026-09-14 核对本机原版 DriveAdapter / ThinkTwice 配置与 agent 源码。此文件是后续适配约束，不是闭环验收记录。

## 不能直接复用六视角模型输入

原版配置 camera_list 顺序均为 `rgb_front, rgb_left, rgb_right, rgb_back`，四路 RGB。DriveAdapter 原始 sensors 定义如下（米、度）：

| ID | x,y,z | yaw | 尺寸 / FOV |
| --- | --- | --- | --- |
| rgb_front | 1.5,0,2.5 | 0 | 1600×900 / 150° |
| rgb_left | 0,-0.3,2.5 | -90 | 1600×900 / 150° |
| rgb_right | 0,0.3,2.5 | 90 | 1600×900 / 150° |
| rgb_back | -1.6,0,2.5 | 180 | 1600×900 / 150° |

LiDAR 位于 0,0,2.5；IMU、GNSS、速度也参与预处理。topdown 是原 agent 消费的调试相机，不能把它误记为第五个模型 RGB。系统辅助六视角/深度/BEV 可独立采集，但必须和模型真正使用的原始四视角分开归档、标注，不伪造标定。

## 时间与状态

- 原版队列容量 31、仿真 20 Hz。配置 history_query_index_lis=[-1,0]；agent 乘 10 后再减 1，实际读取队列 [-11,-1]，相隔十帧，即 0.5 秒，不是相邻两帧。
- 31 步预热不能计作完成 31 次模型推理。验收必须记录真正调用模型的计数、每次输入 frame ID、episode、时间戳；切图/丢帧清空队列并重新预热。
- 原始 union2one 根据 ego 位姿构造历史坐标变换、合并 LiDAR，增加时间通道。不能只复制当前图像/点云来凑两个 sweep。
- DriveAdapter 六维状态由上一控制的 throttle/steer/brake/常数 1，加纵横向速度计算组成。原代码 uses sqrt(max(speed²-(angular_velocity_z×1.5)²,0)) 和 angular_velocity_z×1.5。合成测试中的零状态不应进入真实运行。
- DriveAdapter route mask 为 192×192、5 px/m、ego 距图底 40 px、路线折线宽 16 px，来自当前真实路线与位姿。合成直线 mask 仅用于探针。

## 接入顺序与放行条件

1. 原生进程拥有 CARLA 世界和传感器；隔离 Python 3.10 模型进程只负责推理。不得注入 Python 3.14 CARLA 扩展路径到模型环境。
2. 抽取可复现的原始输入快照，核验原版预处理的颜色顺序、内外参、历史位姿及点云坐标；先离线重放真实快照。
3. 接通原始控制转换，检查有限数值、幅值、帧身份、超时与过期响应；失败安全停车并清理本任务资源，不重复提交控制。
4. 原生静态地图短闭环通过后，验证退出清理、取消、进程故障、跨地图恢复与原始输入归档。
5. 只有完成上述真实验证才开放 UI 模型入口。完整合成网络前向通过不满足放行条件。

已通过的依赖、权重、GPU 和合成推理证据见 [接入进度](OPENDRIVELAB_INTEGRATION.md)。

## 时间身份门禁实现

`src/carla_safety_agent/opendrive_history.py` 新增独立时间身份门禁，按原版 step=-1 的计数在第 32 次有效输入才返回 [-11,-1]。episode 变化、重复/逆序/缺帧或非 20 Hz 时间间隔均清空历史并重新预热；非有限时间等非法身份拒绝并清空。11 项测试通过。

后续增量：`append_sample` 将身份和预处理数据放进同一个有界队列，入队及输出均复制，避免原始 union2one 就地修改污染后续历史；复制失败同时清空身份和数据。新增测试验证复用输入缓冲、输出被修改、旧当前帧随后成为历史帧、跨世界数据清理与复制失败恢复。模块共 14 项测试。

该门禁尚未接入真实模型适配器，因此目前不声称线上模型已具备此保护。下一步由原始单帧预处理提供 payload，替换 agent 独立维护的队列，并完成真实传感器快照重放；不能在原始 agent 外另维护一套不同步的数据队列。

原生执行器后续增量：在获得同步 sensor_data 后、任何模型预处理前调用 `deliver_frame_context`。仅对声明 `set_simulator_frame` 的适配器验证真实 world.id、snapshot.frame/仿真时间与全部传感器帧号并投递 FrameIdentity；不声明接口的原五模型不增加 RPC。错误输入在模型调用前抛出，沿既有 finally 清理。新增 8 项单测，相关 45 项测试通过。尚未用两个剩余模型实机运行，不视为闭环验收。

原版调用桥接增量：`OriginalAgentQueue` 支持原 agent 的 len/popleft/append/[-11,-1] 调用，实际读取同一身份绑定队列。`OriginalHistoryMixin` 消费执行器的 set_simulator_frame；开发用 ThinkTwice wrapper 已添加，但未加入目录或启动脚本。三项测试覆盖原版 42 帧队列协议、上下文只消费一次及跨世界终止。运行中不只清空图像后继续使用旧路线/GPS，而是拒绝并要求重建整个 agent。下一步仍需安全严格权重初始化接入 wrapper（当前沿用原始 setup，尚不可作为验收入口）、依赖导入与真实输入验证。

安全初始化后续增量：ThinkTwice wrapper 在原始 setup 期间局部替换 build_model/load_checkpoint，关闭额外 ResNet 初始化并调用 `strict_model_weights.load_complete_checkpoint`；覆盖键、形状、dtype、有限值校验及加载后精确比对，始终 weights_only=True。函数退出恢复原模块符号。实际完整 1344 项权重通过新加载器，证据 `runs/validation/thinktwice-adapter-loader-20260914-v1.json`；仅 CPU 加载，不是 wrapper 完整 setup 或闭环验收。隔离 Torch 测试拒绝五类错误权重且确认模型未被修改，974 项项目测试通过。下一步完整 setup 的依赖与原版 SAVE_PATH 初始化问题、真实快照推理。

实际 setup 验证：`tools/probe_thinktwice_setup.py` 调用开发 wrapper 的完整 setup，在临时 SAVE_PATH 下严格加载 1344 项权重至 cuda:0，原始单帧与时序 Compose 初始化完成，队列为 OriginalAgentQueue，声明九个传感器 ID。证据 `runs/validation/thinktwice-setup-20260914-v2.json`。通过 __new__ 跳过会连接 CARLA 的基类构造，未生成传感器、未调用 run_step、未驾驶；不能算闭环。v1 原始训练目录 code/ 遮蔽标准库导致 Torch 导入失败，改为先导入 Torch 再加入原始模型目录，v2 通过，失败证据保留。SAVE_PATH 在本次探针中显式设置，未验证缺失该变量的原始 setup 分支。

原始 run_step 链路验证：探针增加显式 `--synthetic-steps`，只替换 tick 输出及 GPS 缓冲更新，原始单帧预处理、union2one、真实网络及 process_action/control_pid 均实际运行。32 帧仅产生一次真实网络调用，输入 [1,2,4,3,448,896]，有限控制输出。证据 `runs/validation/thinktwice-original-steps-20260914-v1.json`。输入为零 RGB 和合成点云/位姿，不验证传感器、路线规划、GPS、世界状态或驾驶质量；不是实际闭环。下一步仍需通过会话管理接入受控原生验收，不绕过会话启动第二个 tick 所有者。

受控启动增量：服务端显式 `CSA_EXPERIMENTAL_THINKTWICE=1` 允许已确认场景以 thinktwice 进入原有会话管理；默认拒绝，DriveAdapter 不放行，公开目录仍未集成。`tools/run_opendrive_native.py` 使用隔离依赖、检查必要会话变量并调用现有 native_executor；不另造 tick/资源清理循环。979 项测试通过。桥接在无活动会话/批次的检查后重启为 PID 657857，已加载开发开关，CARLA 未重启。下一步真实至少 32 帧以上的同地图受控验收；测试后关闭开发开关。此刻尚未启动 ThinkTwice 原生任务。

首次原生实测（后续）：`tools/regression_thinktwice_native.py` 通过会话启动两次四秒任务，均失败，绝非闭环通过。报告 `thinktwice-native-82831191f95c4aa1a53fa8f67c1b8582.json` 对应 fd83813a70ac47e2bcdff73ac6c4e054：速度回调写死 SPEED，而原版为 speed；修正执行器使用声明 ID，三个回归通过。第二份 `thinktwice-native-c0d5c22229a9438e85fa5af0c40fe14e.json` 对应 7ea9b61b56ab424c963aa6e6dea6fcd5：进入 run_step 后 LiDAR 仍为原生对象，缺少 copy；已补 float32 XYZI 独立数组解码与缓冲不共享测试，27 项清理/传感器测试通过。第二项修复尚待实机重试。两次会话均终止为 failed，重启门禁确认无活动任务/批次后关闭开发开关，普通桥接 PID 660998，CARLA 未重启。下一轮重新显式启用并继续同地图实测。

第三次真实运行：22cf2088e7e543c496f8acbca451fbb7，报告 `thinktwice-native-f482218fc49f4a4eb0e4ae7247830b14.json`，Town04 四秒/80 tick，completed/rc0，无碰撞，最近距离 14.11 m。原始 agent 在 step40/50/60/70 保存了真实控制元数据，证明越过预热；非长期驾驶质量验收。**统一采集未通过**：capture-20260914T154629-d88f9e7f 为零帧，验证器明确拒绝。原因是采集触发只查 CAM_*；已改为按声明的 RGB 类型识别，增加实际四视角 NPZ 落盘测试。此修复尚待下一次实机重测，不修饰旧零帧数据。983 项全量测试在此采集增量前通过。任务结束后关闭开发开关，桥接 PID 664826；没有重启 CARLA。报告 ok 仅表示该次进程/场景执行通过，不包含数据完整性。

第四次真实运行与数据验收：a150912c6d9f4498a1c1db52c7dbd980，报告 `thinktwice-native-b4fc8796cbf6416aa474dd8e1094c0ec.json`，completed/rc0，Town04 四秒、无碰撞。`capture-20260914T155103-738f61ef` 的 80 帧通过实际输入覆盖、同步、米制深度、XYZI、BEV 校验；外参 22/23，缺失项不算通过。验收脚本现将 execution_ok 和数据验证分开，零帧不能再得到整体 ok。983 项项目测试通过。浏览器 `browser-models-a5a83e8a-7951-4bab-a214-33c329707108/replay-quality.png` 已查看：六辅助 RGB、点云、顶视和回放索引可见，模型预测因坐标契约未审核仍明确不绘制。当前截图不是模型四摄像头专用面板，也不是预测轨迹验收。任务结束后关闭开发开关，普通桥接 PID 668888。仍需预测输出适配、取消/异常/切图矩阵和 DriveAdapter 实际接入，公开模型目录不放行。

![ThinkTwice 首次有效统一采集回放](../runs/validation/browser-models-a5a83e8a-7951-4bab-a214-33c329707108/replay-quality.png)

预测空间适配增量：PlanningObservation 现在也可观察 agent.model.control_pid，保持原控制返回值、不增加推理。ThinkTwice PID 先保存原 waypoints，随后交换两轴用于以 +Y 为前向的转向角计算，因此保存的 wp_1..4 为 forward/right；本系统转换为 right/forward，再以 ego heading 显示，无 VAD 的虚拟 LiDAR 偏移。控制器源码指纹固定为 bd137dfc6505ad499129335ef6d4d788499b33aeba33a30a896dd22902518ae7；不匹配拒绝。33 项预测测试通过。仍需新一次真实采集确认观察链和叠加效果；旧 80 帧数据没有观察锚点，不回填伪造预测。预测点时间仍为未知，不计算 ADE/FDE。

预测实机检查后续：1609465ad2bd4dda9af35044a3b43eac 正常 completed，80 帧基础数据通过，但预测专项验证失败：上述最初指纹漏了 @force_fp32 装饰器，运行时正确拒绝预测。旧数据 `capture-20260914T155708-fdc8e72e` 保留拒绝状态，不回写。修正指纹为 d4343e889691d61d5521874a312a71775c48a67eacda0c6e8f6a6a5ac2af11c1；实际加载方法的 inspect.getsource 检查通过，证据 `thinktwice-pid-source-20260914-v1.json`。新增 `validate_thinktwice_prediction.py` 分别验证31预热帧与随后预测的来源帧/步数/锚点/空间转换，尚待新录制通过。观察器成功/失败路径对 model 属性补测通过，临时开发开关已关闭，桥接 PID 673430。原生报告 ok 仍只覆盖执行和基础数据，不能代替预测专项验收。

重要更正：389a77c8c27f4a69b117f21167054e6a 的基础采集通过，但 `capture-20260914T160056-572834d9` 预测达数万米、目标点达数百万米，范围检查正确拒绝。根因为原生 launcher 将原始模型目录追加在 Bench2Drive 之后，误加载 Bench2Drive 同名 team_code.planner；其路线转换与原版 _get_position 不一致。已改为 Torch 初始化后前置原始目录，并强制核对 planner.__file__。实际导入检查选择原版，0.00001° 纬度路线增量按同一变换得到约1.113246米。**此前原生 completed/无碰撞仅证明生命周期与采集，不能证明模型输入坐标正确或驾驶能力；模型整体验收仍失败。** 不放宽预测边界，不改旧数据。修复尚待下一次原生重测；开发开关关闭，桥接 PID 677259，987项测试通过于本次导入修复之前。

依赖组合与预测实测最终增量：全目录前置又触发原版旧 agents 导航 API 冲突（8a4005bc9c464d41906b29f34cd1e481），只前置 leaderboard 目录触发旧 leaderboard 包冲突（ece2e770606a4459b5791b7b40f0480d）；两次均在模型运行前失败，记录保留。现先固定本机 leaderboard 包、仅前置原版 team_code 所在目录、保持 CARLA PythonAPI 导航优先，并检查三个来源路径。

修正组合后的 63ec15eee90049ef8a80c64755e79782 completed/rc0，报告 `thinktwice-native-4e12da94ebc74111a643d89280c2f92f.json`；`capture-20260914T160555-f9dd386b` 80 帧基础数据通过，22/23 外参通过。预测专项首次完整通过：31 warmup +49 available，连续帧/步数、同帧锚点、四预测点和空间转换全部核对。浏览器 `browser-models-33b9b002-e841-4b0b-8405-5af16e2d7f0c/replay-quality.png` 已查看，选择第41帧显示米级预测（图幅约13.2米），未计算预测时间/ADE/FDE；截图拍摄时录制仍在进行，最终数量以80帧校验为准。987 项测试通过。实验开关已关闭，普通桥接 PID 681679。仍需异常/取消/切图与模型原始四视角可视化、DriveAdapter 实际接入，不能将短直道空间验证当作全部验收。

![真实 ThinkTwice 预测与记录轨迹空间对比](../runs/validation/browser-models-33b9b002-e841-4b0b-8405-5af16e2d7f0c/replay-quality.png)

四视角显示增量：采集器对实际输入中声明为 RGB 的相机保存独立无损 PNG 与实时 JPG，保留原始 ID/NPZ，不以六辅助视角冒充输入。工作台增加 2×2 模型原始四视角区域（rgb_front/left/right/back），与六视角 RGB/深度区分；放大和有界图像重试复用现有逻辑。旧数据未保存预览时明确提示查看 NPZ，不自动改写旧数据。实时端点仅新增四个固定 ID 白名单。四路 PNG 与原始 BGRA 转换逐像素测试、TypeScript 检查通过；尚待新录制与浏览器图片加载/放大实测，当前桥接未为此重启。

四视角实际验收：525d4931938b4057a8355f381d28ae1b completed/rc0，报告 `thinktwice-native-a5037a25f30b40bf981e7561651981a6.json`。capture-20260914T161230-4aba05f3 的80帧通过增强验证器，包括新增模型RGB预览逐像素匹配原始BGRA及标定尺寸；预测31预热+49有效。浏览器 `browser-models-8f0abb0b-561b-440e-a862-97cb94ba4477` 四张模型图加载成功、正前大图自然宽1600，两个截图已查看。生产构建与987测试通过（最后文案区分实时压缩JPG/录制无损PNG后未重新构建）；该次验证覆盖录制回放，不外推实时端点或所有模型。实验开关在完成后关闭。开始前约15GiB可用，继续大规模采集前重新检查容量，不自动删除历史证据。

![模型原始四视角](../runs/validation/browser-models-8f0abb0b-561b-440e-a862-97cb94ba4477/model-four-views.png)

![原始正前图放大](../runs/validation/browser-models-8f0abb0b-561b-440e-a862-97cb94ba4477/model-front-enlarged.png)

原始蓝图属性审核：此前 NativeSensorRig 仅应用宽高/FOV/tick，遗漏原版 agent_wrapper 的显式 LiDAR、镜头和噪声配置。因此既有80帧证据不代表所有原始输入参数一致。新增 `opendrive_sensor_profile.py`，仅 ThinkTwice wrapper 选择原版属性；执行器发现必需属性不支持时在生成该传感器前拒绝。新增4项回归，项目991项测试与TypeScript通过。

该修正最终运行结果：aac763288b114f079971a132189da3ad completed/rc0，`runs/validation/thinktwice-native-9624aa58f2924a5994f306046d68d666.json` 整体ok；`capture-20260914T162209-4ac2b23f` 80帧基础/原始RGB逐像素验证通过，预测专项31预热+49有效通过。仍为四秒同地图验证，不包含取消/异常/跨图或未来轨迹精度。

修正后实机任务 aac763288b114f079971a132189da3ad 正在验收。只读观察在 wait_for_tick 后确认模型 LiDAR actor1160 实际为64线、85m、10Hz、600000点/秒、垂直[-30,10]；辅助LiDAR actor1176仍为32线、80m、20Hz、128000点/秒，两者不混同。IMU actor1161实际噪声标准差为加速度(.001,.001,.015)、陀螺仪(.001,.001,.001)。首个未等快照的独立客户端查询返回空列表，不据此判断传感器不存在。原生统一20Hz调度将sensor_tick设0并记录原请求周期；未新增tick所有者。此处只记录实测属性，最终完成/采集结果另附。

推理中取消验收：`regression_thinktwice_native.py --cancel-after-inference` 新增不录制数据的取消路径，必须看到至少32个完成步骤、使用原execution_id停止，并要求stopped/130和五秒异步零传感器健康检查，不能把提前失败或其他任务退出算通过。三项探针回归验证预热不提前取消、完成态不能冒充停止、身份变化不能误停。

DriveAdapter wrapper初始化增量：新增 development-only `integration/opendrive/driveadapter_agent.py`，复用绑定帧身份的队列；将已验证的稀疏权重转换移入运行时包，严格加载器显式选择RSCK→KRSC并继续完整键/形状/dtype/有限值及加载后精确校验。原版ev_mask.npy固定相对路径改为源仓库内的同一文件，不修改进程cwd；仅跳过辅助Roach参数初始化，随后完整权重强制覆盖。

DriveAdapter输入/原版run_step增量：两个原始agent_wrapper.py逐字节一致，SHA256均为7ed7ba618806eec5348949110d444eeb8eaf0d435dd7735a73f51c3f977bef70。DriveAdapter wrapper现显式选择同一蓝图属性配置，但保留自己的192×192 topdown（ThinkTwice为512×512），两个尺寸保留回归通过。历史队列原版同样31预热、[-11,-1]选择，DriveAdapter另给历史项附加previous_one_action，未替换这段原始逻辑。

DriveAdapter受控原生入口已实现：独立CSA_EXPERIMENTAL_DRIVEADAPTER=1，不受ThinkTwice开关影响；默认禁用，公共目录不放行。launcher按模型选择原版仓库、配置、权重与wrapper，继续校验依赖来源并沿原会话执行。新增5项独立门禁测试，1001项目测试通过。

首次实机2fe48d8282864b58a0b3c0444ed71b23失败，报告driveadapter-native-d7c13209b73745d1baeaf35f2bf7977c.json：原版set_global_plan额外需要wp_route，未进入推理；未初始化model时destroy再次报错，异常链保留。已补opt-in set_native_global_plan，通过当前地图将世界路线转换为实际waypoint，空路线拒绝；原版get_ego对接本机get_hero_actor，未初始化model的destroy不再调用原版删除。修复尚待实机重测，不算闭环或取消通过。实验入口已关闭，普通桥接PID703894，未删除旧证据。

后续实机80f56662fdc54252a1da955bf6545460通过路线设置和传感器生成，但get_hero_actor返回None，未推理；报告driveadapter-native-a1bead25743c44f09ee2ead3362c23d4.json保留失败。原因是原生执行器车辆不在benchmark provider的actor池，不能通过重命名getter解决。现执行器通过opt-in set_native_ego直接绑定本任务的活车辆，原版_init只在局部get_ego调用返回这一真实actor；缺失/死亡时拒绝，不扫描或选择其他主车。新增五项路线、部分初始化清理与主车绑定回归。

修正后e6a7711a8e1c4730b3479dfc08e9cd11真实推理后取消通过，报告driveadapter-native-e0534934d4484b8586e9d674d14b4d97.json：stopped/130，五秒异步推进、同世界、零传感器。本轮未开启统一采集，不算完整80帧、保存分支、预测可视化或切图验收。1006项目测试通过；实验开关关闭，普通桥接PID707063，CARLA未重启。下一步完整运行及真实采集验证。

DriveAdapter首次完整采集：b167f7d415cc436cac5cb84dbe34bb0f completed/rc0，报告driveadapter-native-875f66e3c6254a0080a19e3035be2eae.json整体ok。capture-20260914T164050-27b18bb2恰好80帧、saved、无error/stop_reason，原始输入覆盖、同步、多模态与RGB预览逐像素校验通过。验收条件从>=32收紧到完整80帧且最终saved/无错误，新增9项反例测试，1015项目测试通过。后验5秒21次检查：同episode4926267799737637651，帧5621345→5623453，异步、零传感器；实验开关关闭，普通桥接PID712206。

浏览器首次f9867498-647b-4d26-a52a-e6baa2c4ab8e检查早于第41帧落盘而失败，保留证据；确认50帧后同数据集重试browser-models-e188a49e-ea7f-4cbf-bae4-a64121555b08成功，模型四图加载与正前1600像素大图通过，两张截图已查看。截图拍摄时录制尚在进行，最终帧数以上述校验为准。图像包含草地/道路外观及既存渲染表现，本次只证明输入保存与显示一致，不证明道路视觉正确或驾驶能力；预测坐标适配未审完、无预测轨迹验收。仍需预测/跨图/故障与更长路线，不把四秒成功算全面接入。

![DriveAdapter原始四视角](../runs/validation/browser-models-e188a49e-ea7f-4cbf-bae4-a64121555b08/model-four-views.png)

![DriveAdapter正前大图](../runs/validation/browser-models-e188a49e-ea7f-4cbf-bae4-a64121555b08/model-front-enlarged.png)

DriveAdapter预测空间适配：重新提取两个原版控制器（含装饰器）源码，SHA均为d4343e889691d61d5521874a312a71775c48a67eacda0c6e8f6a6a5ac2af11c1；原版先保存waypoints再交换轴用于转向，故归档wp_1..4为forward/right。新增driveadapter-experimental别名、model.control_pid来源和ego heading零偏移映射，保留源码指纹、同帧锚点与预热检查；无时间契约，不计算ADE/FDE。37项轨迹测试通过。

只读检查现有capture-20260914T164050-27b18bb2：31帧预热无锚点，随后49帧原始预测及同帧锚点通过空间布局检查，最大绝对轴11.441370964m。该检查没有改写旧frame.json，旧数据仍保留未审核坐标状态；不能当作新增capture_prediction路径或浏览器叠加已实测，仍需新录制验证。公开入口不变，桥接未重启。

验收门槛补齐：validate_thinktwice_prediction.py现按显式--model验证ThinkTwice或DriveAdapter，模型身份不匹配拒绝。原生完整采集harness必须同时通过基础数据和预测专项，保存各自输出，不再将基础数据ok误作为模型预测验收。新增预测失败反例；ThinkTwice既有capture-20260914T162209-4ac2b23f仍31预热+49有效通过，旧DriveAdapter capture-20260914T164050-27b18bb2因原录制未启用空间契约而明确失败，符合预期，未改写数据。新harness不追溯修改此前报告含义。新DriveAdapter预测录制/叠加尚待实测，当前磁盘约5.2GiB，未删除历史记录。

固定80帧验收录制准入：新增acceptance_storage，按实测约3GiB的固定rig预算4GiB并保留2GiB主机空间，在保存场景或启动任务之前检查6GiB可用空间，记录估计值；不是任意rig的容量规划，也不是磁盘配额，逐帧reserve仍保留。低于阈值不开始录制、不删除历史；不录制的取消验收不受该固定预算阻挡。四项边界/无副作用测试通过。当前5.2GiB实机只读准入明确拒绝，因此新80帧预测录制暂待容量处理；其他非录制开发仍可继续，整体目标未标记阻塞或完成。

停止失败分类修正：原_finish_e2e在stopping状态下将任意退出码当作stopped，能掩盖模型/清理异常甚至SIGSEGV。现只有请求停止后的0/130归类stopped，其余非零归类failed/process_exit；无停止请求的130同样保留失败原因。回归覆盖停止后1/-11失败及普通中断成功，修正旧测试中将stopping+1当作成功停止的错误期望。此为状态分类修复，不声称已经注入真实模型崩溃验证，桥接尚未加载该改动。磁盘删除仍未获确认，没有删除数据。

结果读取健壮性增量：_benchmark_result_failed拒绝空对象、非对象、非法UTF-8以及存在但结构异常/缺状态的_checkpoint，避免空结果默认成功或None/list导致完成监视线程抛异常；失败状态大小写/空白标准化。133项桥接测试通过。无_checkpoint的原生结果仍沿旧路径，不将其称作全面schema验证；尚未在运行桥接加载本增量，未注入真实结果损坏测试。

后续结果兼容检查：只读扫描runs/benchmark下36份真实历史结果，1份Completed不报失败，31份Failed及4份不完整均报失败；另实际原生结果aac763对应JSON保持兼容。增加4项零退出码+损坏结果文件的_finish_e2e贯通测试，确保最终会话failed/benchmark_result而非监视线程中断。确认空闲后已加载普通桥接PID728962，实验开关关闭。未重写历史结果，也未将历史基准失败当作本轮CARLA崩溃。

原生结果结构增量：无_checkpoint分支不再接受任意非空JSON，识别原生模型schema及顶层规则测评格式，检查场景ID一致、驾驶status、collision布尔、原因列表和非负有限指标。有效驾驶status=failed仍是已完成执行，不冒充程序故障。142项桥接测试通过；现存原生模型及规则结果各一份只读兼容验证通过。暂不声称执行ID/场景hash已在此分支核验（报告模块另有校验），本增量尚未重新加载运行桥接。

结果归属增量：新启动的原生run/rule-run在内存任务记录保存expected_execution_id及expected_scenario_sha256，完成判定将其传给结果校验，缺失/不同的结果归属拒绝；preset-run不强加本项目原生结果字段。新增5项身份匹配/旧执行/旧场景/缺字段测试，147项桥接测试通过。此为结果声明的ID/hash匹配，尚非重新计算嵌入scenario内容哈希；运行服务尚未加载本增量。

结果内容归属补齐：当任务提供预期场景哈希时，重新按场景归档的canonical JSON规则计算结果内scenario内容哈希，而非只相信sha256标签；拒绝内容修改、非对象及NaN等非法场景。150项桥接测试通过；实际原生模型aac763及规则结果各一份执行ID/场景标签/内容哈希完整兼容检查通过。确认无活动任务后加载桥接，未启动新录制、未修改历史文件；这是离线真实结果兼容与服务加载，不是新的完整模型闭环验收。

加载后真实完成链验证：regression_rule_session.py新增显式--no-capture，仅覆盖执行和资源恢复，不伪造数据验收；与依赖采集帧的--stop不能同时使用。实际规则任务b71ac1c58c6b4a44b97fd6f2d6f9ddf0 completed，结果身份/场景内容匹配、重复启动拒绝、资源journal recovered、8051 TrafficManager停止、世界异步及零传感器检查通过。报告runs/validation/rule-session-b71ac1c58c6b4a44b97fd6f2d6f9ddf0.json明确dataset=null/capture_verified=false。此为规则任务验证，不外推新增模型或故障矩阵通过。

取消语义修正：规则任务在主动停止时可正常以0退出并保存部分stopped结果，不应套用完整测评schema后标benchmark_failed。完成监视现在仅在非stopping、无startup_error且0退出时评估结果，并显式记录result_assessed；主动停止为false，不冒充测评通过。停止后非正常退出仍按上一修复保留process_exit失败。151项桥接测试通过，包括确保取消路径不调用完成结果校验。运行桥接尚未加载本增量，仍待真实停止回归。

取消语义实机回归：加载普通桥接PID735987后，regression_rule_session.py --no-capture --stop仅通过snapshot观察现有tick所有者推进，未主动tick；记录帧6309821→6309826后按本execution_id停止。63c3edca4a16444db97eca8934783789最终stopped，result_assessed=false/benchmark_failed=false/failure_category=null；重复启动拒绝、场景与执行身份、资源recovered、8051管理器停止、异步零传感器检查通过。报告runs/validation/rule-session-63c3edca4a16444db97eca8934783789.json；dataset=null/capture_verified=false，不外推采集中取消或模型故障矩阵。

`runs/validation/driveadapter-original-steps-20260914-v1.json`通过32帧原版run_step合成验证：真实预处理、union2one、完整网络和最终控制转换运行，31帧预热后一次推理，图像[1,2,4,3,448,896]，控制steer=-0.0316087/throttle=0/brake=1且有限。tick输出、GPS缓冲更新和192²路线掩码为明确的合成替代，不声称真实传感器、路线或驾驶验证；SAVE分支(step40)未覆盖。996项目测试通过。下一步仍为通过原会话管理接通DriveAdapter真实路线和传感器，不直接启动第二个tick所有者。

`driveadapter-setup-20260914-v1.json`因探针误选项目精简leaderboard包失败，修正为优先本机Bench2Drive包并校验来源后，v2完整setup通过：1289项严格权重加载到cuda:0，OriginalAgentQueue和原版单帧/时序预处理初始化完成。未执行基类CARLA构造、传感器或run_step，不是实际闭环；DriveAdapter专用传感器参数仍待审核，入口不放行。994项目测试及严格权重五类拒绝专项通过，原失败记录保留。

实机 `200b50407ccd4a1290d854a74bb10197` 在第34个完成步骤发送停止，最终stopped/130、无session错误；同一episode 4926267799737637651，5秒21次检查帧5310672→5312866、异步、零传感器。报告 `runs/validation/thinktwice-native-88244d9bec6b44719ee29770732a3f26.json`。本次未录制，不是采集中取消验证；仍需故障、跨图及DriveAdapter接入。实验开关已关闭，普通桥接PID697241，CARLA未重启，历史数据未删除。

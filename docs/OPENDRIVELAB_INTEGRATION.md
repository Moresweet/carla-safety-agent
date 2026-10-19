# DriveAdapter / ThinkTwice 接入状态

## 迁移依赖清单增量（2026-09-14）

新增源码恢复API `source_bundle.restore_source(archive, destination)`：读取有界、不可变内存快照并完整验证后，才创建全新目标目录；不合并、不覆盖、不运行脚本，恢复已验证文件与权限，并写入SOURCE_RESTORE_RECEIPT.json保留遗漏警告。损坏包不创建目标，已有目标直接拒绝；写入失败保留部分目录供检查，不自动删除。25项源码包测试通过，含往返内容/执行权限/警告保持。恢复的是已提交源码，不恢复.git历史、依赖、权重、未提交内容或运行环境；尚未接入前端恢复按钮，不能算完整项目迁移完成。

源码归档遗漏提示现已持久化：manifest增加可选uncommitted_source_omitted，验证归档时返回清单与警告；旧v1归档仍可读，但缺少字段明确标为未知，不推断为干净工作树。拒绝重复、非源路径、越界及错误类型。23项源码归档测试通过，包括导出后重新打开保留警告和旧格式兼容。此处只记录文件名、不备份其内容；完整当前源码迁移仍未完成。

源码导出遗漏提示增量：export_source仍保持已提交快照语义和现有归档格式，但返回uncommitted_source_omitted、has_omitted_uncommitted_source及warnings，列出过滤范围内未提交的已跟踪/未跟踪源文件名，不读取这些内容、不自动提交。18项源码包测试通过，包括脏源文件仍不打包且必须警告、私有data文件不被列为源代码。此提示属于导出返回结果，尚未声称前端已展示；不是当前工作树备份实现。

新增 `python3 tools/inventory_original_model_dependencies.py --verify <清单JSON>`：只读核对已列文件大小与SHA256，缺失/内容变化返回失败，拒绝相对越界、绝对路径、重复路径及逃出项目的符号链接。现有v1清单19文件实测全部匹配，5项变更/缺失/路径回归通过。该验证只覆盖清单文件字节，不检查完整源码树、安装环境或实际运行，`restoration_verified`仍为false；不是迁移恢复验收完成。

运行 `python3 tools/inventory_original_model_dependencies.py --output <新JSON路径>` 可生成只读依赖收据，不导入Torch、不加载权重、不下载或复制数据。记录两个源仓库HEAD及跟踪文件脏状态、实际权重大小/SHA256、配置、agent、planner、传感器创建代码、DriveAdapter路线mask和本项目关键适配文件。

已生成 `runs/validation/original-model-dependencies-20260914-v1.json`。这些SHA256是本机指纹，不是上游签名或真实性证明。源码迁移包当前仅导出已提交代码，运行目录、权重、编译库和未提交适配不会自动包含；收据也不包含这些字节，不得声称可独立恢复。仍需完整环境/编译依赖锁定及目标机恢复验收，八阶段迁移目标未完成。模型真实接入进展以[传感器契约日志](OPENDRIVELAB_SENSOR_CONTRACT.md)后续条目为准，下文保留历史核查记录。

2026-09-11核查：二者官方原版均提供代码和预训练权重，旧界面NOT RELEASED不准确。
现在改为NOT INTEGRATED：本机执行接口尚未接入，不能仅放入同名文件便启用运行。
输入契约和执行框架也显示待接入，不默认宣称六摄像头。

官方来源：

- [DriveAdapter](https://github.com/OpenDriveLab/DriveAdapter)及[安装说明](https://github.com/OpenDriveLab/DriveAdapter/blob/main/docs/INSTALL.md)。
- [ThinkTwice](https://github.com/OpenDriveLab/ThinkTwice)及[安装说明](https://github.com/OpenDriveLab/ThinkTwice/blob/main/docs/INSTALL.md)。

官方原版文档面向Python3.7、PyTorch1.12.1/CUDA11.3及CARLA0.9.10.1。
不能把这些原版权重冒充当前Bench2Drive配置对应的权重，或照抄旧安装步骤覆盖现有五模型环境。
真实本机GPU为RTX5070 Ti/16GB；沙箱内nvidia-smi不可见不等于驱动故障，提升只读权限后正常。

独立准备目录为.runtime/external-models，未纳入Git或源码迁移包。
已取得官方源码：ThinkTwice e9cf2fc078f6ab8175b1a4929faaa8be55f3aa97；
DriveAdapter 4275652fde2e87ba85f562ec65d5f1f26c38df7e。
MMDetection3D官方1.0分支固定47285b3f1e9dba358e98fcd12e523cfd0769c876。
ThinkTwice189K权重已完整下载：515776025字节，ZIP内部CRC检查通过，
使用torch.load(weights_only=True, map_location='cpu')安全读取到1344条state_dict记录。
本机计算SHA256为6c86b4ad020cb4b5b67d77929d884a878172a5dc56bd8103ff614f68a828d1b5；
这不是上游公布的校验值，也不证明模型推理通过。
DriveAdapter189K权重也已完整下载：646348560字节、ZIP CRC通过，安全CPU读取1289条state_dict记录。
本机SHA256为62abeb9275510c0e43acee9ebb9518c2aa19f59b0307a31827b755976590c949，非官方公布校验值。

隔离兼容检查使用单独Python包目录，不改动原五模型环境；tools/probe_opendrive_environment.py
只做显式指定依赖导入及可选微型稀疏GPU算子对照，不连接CARLA，不证明模型已能推理。
复用现有编译算子必须验证ABI/API，而不是伪造版本号。
现有Bench2Drive算子实际缺少active_rotated_filter_forward，复用检查失败。
已独立编译MMCV1.7.0完整算子，使用Torch2.7.1/cu128、CUDA12.8、Conda GCC11.4及其sysroot、
sm_120和MAX_JOBS=1；仅隔离源码将两个THCAtomics头文件引用改为ATen/cuda/Atomic.cuh，
并将C++14改为Torch要求的C++17。128个编译步骤及链接成功，不替换现有运行环境。
扩展SHA256为5106bbb9dd63dd2e9efb35b823f6ede9bfd61d097f84d1e841ddc8937798eb5a。
完整依赖导入和可变形注意力FP32前向/反向CPU对照通过，报告opendrive-full-dependencies-20260911-v1.json；
该报告同时复测稀疏卷积和voxel_pooling。没有外推为全部MMCV算子均已验证。
spconv-cu126 2.3.8使用独立cumm-cu126 0.7.11覆盖目录，以满足其小于0.8的版本约束。
微型3×3×3稀疏卷积GPU数值对照已通过FP32和FP16，两相邻体素的32通道输出均为预期2016。
这只验证该算子路径，不替代整网推理、其他稀疏算子或真实闭环验收。
系统GCC12触发CUDA12.8与系统glibc的sinpi/cospi/rsqrt异常声明冲突；改用已有Conda编译器，
没有修改系统或原环境的头文件。CPATH显式指向CUDA targets/x86_64-linux/include。
原版voxel_pooling已独立编译成功，并通过GPU前向/反向、重复体素求和、越界点忽略对照；
保留Tensor.type弃用警告，未修改该上游内核。编译入口须先import torch再chdir，避免上游code目录遮蔽标准库。

状态门控增量935项完整Python测试通过；最终文字浏览器517215d2-9d8e-44a5-9cec-a39b0cfe1234
确认5个已有模型READY，二者NOT INTEGRATED且禁用，已查看下半屏截图。
后续兼容适配及实际推理/闭环/采集仍在进行，不据此将两种算法加入可运行矩阵。

隔离MMCV源码调整记录在integration/uniad/opendrive-mmcv17-torch27.patch；
它是进行中的兼容补丁，不宣称已覆盖所有编译错误或完成运行验收。
隔离增量依赖清单为integration/uniad/opendrive-isolated-requirements.txt；不要直接安装进五模型环境。
MMCV源码包构建需--no-build-isolation，避免新setuptools移除pkg_resources导致元数据失败。
算子证据文件runs/validation/opendrive-sparse-voxel-20260911.json记录实际PASS；
--report只创建新文件，已有报告不会被覆盖。
thinktwice-strict-load-20260911-v2.json已严格加载1344条权重，缺失/多余/形状冲突均为空。
关闭ResNet额外预训练下载仅用于完整权重覆盖的构造，不容许保留随机层。

注意：thinktwice-synthetic-forward-20260911-v2.json虽然记录有限张量与ok=true，
进程尾部实际打印了ms_deformable_im2col_cuda invalid configuration argument，**此次整网测试不予验收**。
旧MMCV仅printf且清除CUDA错误，可能掩盖未成功计算的输出；正在增加真实异常传播定位参数。
原始失败/不完整报告保留，不覆盖或将其列入真实闭环矩阵。

## 2026-09-14 后续验证（覆盖前段“正在定位”状态）

ThinkTwice v3 将 CUDA 错误实际抛出；空查询 attention 的前向/反向按零元素处理后，v4 完整尺寸合成推理通过。证据 `runs/validation/thinktwice-synthetic-forward-20260911-v4.json`，不属于 CARLA 闭环。

DriveAdapter：`tools/build_opendrive_voxel.py` 使用本机 CUDA 12.8 / sm_120 编译原始算子。安全加载完整公开权重，跳过仅初始化参数的附属 Roach pickle 加载，随后强制完整严格覆盖；未使用不安全反序列化。1289 项权重无缺失、无额外项、无形状冲突。

原版稀疏权重 RSCK 与当前 spconv KRSC 不同；`tools/legacy_sparse_weights.py` 仅转换真实 SparseConvolution 的 3D 权重并标注转换后的模块 metadata version=2，避免 MMDetection3D 再次转换。不会伪造依赖版本。严格加载后每个张量与转换后的 state 完全一致；三个单元测试检查坐标映射、元数据不变性、错误布局拒绝。

证据链（全部保留）：v1 缺原始算子；v2 权重布局冲突；v3 元数据导致重复转换；v4 严格加载通过；v5 GPU 对 GPU 基准精度不符；v6 换独立 CPU float64 基准通过且不放宽误差；v7 完整合成前向通过。v6 同时验证原版体素池化前向/反向、重复累加与越界忽略。

最终合成报告 `runs/validation/driveadapter-synthetic-20260914-v7.json`：四摄像头两时刻 [1,2,4,3,448,896]、10000 点、六维合成状态和 192×192 合成路线 mask，原始网络返回有限轨迹 [1,4,2] 与 BEV 分割 [1,23,192,192]。这不验证真实相机标定、时间同步、车辆控制或驾驶质量。两模型入口仍是 NOT INTEGRATED。

接下来需要原始相机/历史帧预处理、CARLA 路线 mask 和状态构造、隔离进程推理协议、原始控制转换、资源归属清理及真实短闭环验收。不得用现有六视角数据直接冒充模型原始四视角输入。

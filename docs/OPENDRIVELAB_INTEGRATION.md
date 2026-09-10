# DriveAdapter / ThinkTwice 接入状态

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
ThinkTwice189K权重已完整下载：515776025字节，ZIP内部CRC检查通过，
使用torch.load(weights_only=True, map_location='cpu')安全读取到1344条state_dict记录。
本机计算SHA256为6c86b4ad020cb4b5b67d77929d884a878172a5dc56bd8103ff614f68a828d1b5；
这不是上游公布的校验值，也不证明模型推理通过。DriveAdapter权重尚未下载。

隔离兼容检查使用单独Python包目录，不改动原五模型环境；tools/probe_opendrive_environment.py
只做显式指定依赖导入及可选微型稀疏GPU算子对照，不连接CARLA，不证明模型已能推理。
复用现有编译算子必须验证ABI/API，而不是伪造版本号。
现有Bench2Drive算子实际缺少active_rotated_filter_forward，复用检查失败。
正在独立编译MMCV1.7.0完整算子，使用Torch2.7.1/cu128、CUDA12.8、Conda GCC11.4及其sysroot、
sm_120和MAX_JOBS=1；仅隔离源码将两个THCAtomics头文件引用改为ATen/cuda/Atomic.cuh，
并将C++14改为Torch要求的C++17。尚未完成编译或数值验收，不替换现有运行环境。
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

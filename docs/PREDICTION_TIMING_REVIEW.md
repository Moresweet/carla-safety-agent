# 预测点时间契约审查

状态：进行中，尚不允许据此开启 ADE/FDE。

## 当前 VAD 权重元数据核查

实际目录 `Bench2DriveZoo/ckpts/vad_b2d_base.pth` 存在（699792372字节），benchmark_catalog与run_benchmark_preset指向该权重及VAD_base_e2e_b2d配置。agent用Config.fromfile并strict=True加载权重；输出在vad_b2d_agent.py:394进行cumsum，符合训练偏移标签累积成空间点的路径。

使用zipfile读取archive/data.pkl并以pickletools扫描字符串操作码，没有执行pickle反序列化。权重内38765字符配置声明B2D_VAD_Dataset、future_frames=6，没有sample_interval覆盖。然而训练索引名称为train_info_0520.pkl/val_info_0520.pkl，而当前仓库配置指向b2d_infos_train_meta.pkl/b2d_infos_val_meta.pkl。因此“当前仓库源码等于当时训练源码/数据”仍不能直接认定。

以上四种索引名在本地Bench2DriveZoo/data递归查找均不存在。此范围内无法验证训练frame_idx连续性；不扩展成全磁盘不存在的断言，也不因文件名不同断言权重不兼容。

- 权重SHA256：0f2d48b5c6cdb06d0dffb21612791fe740f3f5c7273b3b5e78e1f19e4a527eab
- 权重内配置文本SHA256：4ec6eda882645f0ef3c00d4d6736a4d6063b322dd2f01a141f896b9f948834fd

后续所需证据缩小为该权重训练数据/源码版本或明确时间契约；现有证据已确认实际权重的模型分支与6点配置，不再仅依赖仓库默认配置，但尚不启用ADE/FDE。

## VAD 的 Bench2Drive 专用训练链（本次新增证据）

核对的是本地 `Bench2DriveZoo/mmcv/datasets/B2D_vad_dataset.py`，不是仓库同时包含的 nuScenes converter。后者的0.5秒常量不能直接证明本项目checkpoint。

- B2D_vad_dataset.py:41 默认 sample_interval=5，:166 明确 timestamp=frame_idx/10；:229 将该间隔传入 get_ego_trajs。
- :352–376 以数据列表索引每5项取未来位置，转到当前 LiDAR 坐标，再做相邻点差分；返回的是偏移序列和有效掩码，不是直接的绝对位置序列。
- prepare_B2D.py:205–216 按标注文件数字编号排序，frame_idx 来自文件名。因标签取的是列表索引，只有文件编号连续、预处理无删帧时，“5项=0.5秒”才成立；不能仅由 timestamp 公式推定所有标签间隔恒定。
- VAD_base_e2e_b2d.py:138 配置 future_frames=6，未发现该配置覆盖 sample_interval。候选预测时域为0.5至3.0秒，但仍缺当前权重训练来源及序列连续性证据。

下一步可针对实际训练info的同route相邻frame_idx审计连续性，并核对checkpoint实际加载配置/输出累计路径。无需继续用当前20Hz控制频率猜时间，也不应转用nuScenes预处理常量。未改变生产timing_verified、point_dt_s或历史录制。

源码 SHA256：

- B2D_vad_dataset.py：a4971a4b971e4056335a097985afd1338ecf7aa2947ca8b1e5c9c24ae47fc43f
- prepare_B2D.py：6b7cbaa951f8669408340bc21659be8ffcbcae85e97b3895559a2dedfca52adf
- VAD_base_e2e_b2d.py：e43af9c2e0b74c9410e98e8cce53b26e635a20308ebeda9b89cbfafcd1b4a209

2026-09-29 本地代码证据：

- `Bench2DriveZoo-tcp-admlp/TCP/config.py` 的 pred_len=4；点数不证明时间间隔。
- `TCP/data.py` 165–175 行使用 future_x/future_y 的四点生成训练 waypoint。
- `tools/gen_tcp_data.py` 192 行使用 `full_seq_x[i+5:i+FUTURE_FRAMES+5:5]`，说明取序列索引 +5、+10…；`tools/gen_admlp_data.py` 128 行也存在该步长。
- 这里的索引不是已证明的 CARLA tick。必须继续追溯 full_seq 的生成、原始数据保存频率、采样/过滤方式及当前 checkpoint 对应训练配置，不能直接乘当前模拟器0.05秒。
- 在线 agent 的控制调用频率或保存频率不能独立证明训练标签的未来点时间。

下一步：核对两套预处理的输入序列构造与数据生产者；建立与模型/训练配置绑定的时间证据，再实现按预测源时间匹配未来姿态的指标。证据不足的模型和旧录制继续 timing_verified=false，禁止回写旧数据为已验证。

## 数据生产端追溯增量

- TCP 预处理逐个读取连续编号 `anno/{i:05}.json.gz` 的 x/y/theta，full_seq 索引对应保存标注序号，不是 CARLA 原始 frame ID。
- 本地 `Bench2Drive/tools/data_collect.py` 的 Env_Manager 声明 frame_rate=10.0，save 使用 self.count 作为文件编号。这支持“若每个计数按10 Hz保存，则5个索引为0.5秒”的候选解释，但不是已验证结论。
- 在本地 tools/leaderboard Python 源码范围未找到 Env_Manager 的实例化/保存调度及 self.count 的递增来源；无法仅凭类常量证明实际标注间隔、丢帧处理或训练数据版本。
- TCP/ADMLP 仓库 README 明确分别使用这两个预处理脚本，checkpoint 下载说明不含具体训练数据时间证明。

因此下一项证据应来自原始标注的连续时间戳或完整采集调度源码及checkpoint训练来源。当前不改生产 point_dt_s，不采用0.25秒（当前20 Hz乘索引5）或0.5秒作为未经验证的默认值。其他模型的时间契约仍可独立推进，这不是整个项目的阻塞。

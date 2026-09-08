# 对象来源、UV 核验、多模态采集与 ROS Sensor Wall

## 本次实现

- Scene Object Manager 增加来源过滤及中文标记：场景原有、用户新增、评测生成。来源记录保存到 `.runtime/actor-provenance.json`，按 CARLA episode 和 actor/type 区分，避免换图后的 ID 复用。记录启用之前、没有历史来源记录的对象不能追溯可靠来源；首次发现按 existing 处理。
- `/assets/uv-audit` 核验网页导出资产。本机 41/41 个车辆导出网格含有效结构的 UV0 数据。此核验不等于全部材质槽、全部 Unreal 资产 UV 均正确。建筑、道路、行人、普通道具尚未完成真实网格/UV/材质槽导出。原非车辆代理几何预览已替换为明确提示和 CARLA 当前观察视角实景取景。先聚焦、应用纹理再刷新；不是未应用草稿的 3D 预览。
- 闭环执行进程保存模型处理前的原始输入，同时拥有辅助深度、LiDAR 和顶视传感器。网页和 ROS 只消费数据，不推进仿真、不重载地图、不另起评测传感器组。
- Collect Data 支持录制/停止保存、采样间隔、数据集选择、逐帧、时间轴、倍速播放、RGB/深度切换、大图及原始输入 NPZ 下载。
- 网页六视角按左前/正前/右前、左后/正后/右后排列，另列 BEV 点云、顶视 RGB、模型预测轨迹。
- 独立 ROS rqt 插件 Sensor Wall：3×3 可缩放布局，六 RGB、正前深度、BEV 点云、顶视 RGB；双击大图；未收到及过期数据提示。使用 Qt 6 枚举，GUI 线程更新图像。

## 数据约定和边界

数据默认保存到项目 `.runtime/generated-scenarios/capture-*`。迁移时需要连同这些目录一起复制；不要只迁移 Git 代码。

每个数据集有 manifest.json、calibration.json、index.json。每个已提交样本包含：

- `model_input.npz`：原始模型数组（BGRA 摄像头、IMU、GPS 等，保持输入 dtype）；字典型标量另存 frame.json。
- 六个 `CAM_*.png`：无损 RGB。模型没有的方向由辅助相机补齐，并标明不是模型实际输入。
- 六个 `DEPTH_CAM_*.npy`：640 像素宽、保持源相机纵横比、相同外参/FOV、米值深度。新版本显式 float32；最初两份验证数据在 NumPy 1.23 下保存为 float64，数值可正确读取，未覆写历史数据。
- `LIDAR.npy`：辅助 XYZI 点云，CARLA 传感器坐标（x 前/y 右/z 上）。
- `BEV_POINTS.png`：点云投影，前方朝上、±60m；`BEV_RGB.png` 是顶视相机，不是语义 BEV 真值。
- `frame.json`：传感器帧号、同步状态、模型控制/预测轨迹、自车变换和速度、附近 actor 变换/包围盒。

六路 RGB 与辅助传感器按 CARLA 帧号对齐；不完整样本跳过并计数。原始数据和预览分离，实时 JPEG 不作为训练数据。录制限制：网页单次最多 2000 样本、20 GiB，保留至少 1 GiB 磁盘余量。写盘会增加墙钟耗时，不能当实时性能基准。

这里的回放是多模态数据回放，不是 CARLA 世界状态重演。旧版无 index 的数据不会伪装成完整六视角数据。当前多模态录制依赖正在运行的闭环评测；早期独立 ScenarioGenerator 的旧录制格式未自动转换。预测轨迹不是未来真值轨迹。其他模型的新增辅助采集尚未逐个完成本轮实机回归。

## ROS 启动

在项目根目录先构建（本机已构建）：

```bash
source /opt/ros/lyrical/setup.bash
colcon --log-base .runtime/ros-log build --base-paths ros2 \
  --build-base .runtime/ros-build --install-base .runtime/ros-install --symlink-install
bash scripts/start_sensor_wall.sh
```

然后在网页开启闭环测试。脚本启动 `capture_relay` 与正式 rqt 插件，退出窗口时结束其 relay。不要同时启动旧版主动创建传感器的 ROS bridge 参与评测。

Relay 发布 `/carla/ego/camera/{front_left,front,front_right,rear_left,rear,rear_right}/image` 和 camera_info，六路 `/carla/ego/depth/{方向}/image`（32FC1）、正前 `/carla/ego/depth/image`、`/carla/ego/lidar/points`、`/carla/ego/bev/image`。点云转换为 ROS y 向左。此 relay 暂不提供完整 TF 树，不能把插件内二维点云显示等同 RViz 地图叠加已经完成。

## 验证记录（2026-09-07）

- Python：43 个测试通过；TypeScript 无错误；前端生产构建通过。
- 两次本机 VAD Town04 route #26406 采集，分别 8、3 个已提交样本，逐样本校验同步、六路 RGB 与 NPZ 逐像素一致、深度范围、XYZI、BEV 可解码。
- 网页实际操作：数据集切换、下一帧、播放到末尾自动停止、深度切换、大图、Escape 关闭通过。
- ROS 真正发布/订阅后九个 tile 全部收到图像；离屏 Qt 渲染已目检，见 `runs/validation/sensor-wall-20260907.png`。正式 `rqt --standalone carla_safety_visualization.sensor_wall.SensorWall` 入口也成功加载。未声称用户桌面窗口已长期常驻。
- CARLA 实景取景接口返回可解码 JPEG；测试停止后 native server 仍可连接、synchronous_mode=False、sensor.* 数量为 0。
- 捕获到上游先销毁 ego 子传感器再调用 agent.destroy 的重复清理警告；现已提前释放辅助传感器并增加清理顺序单测。最后这个清理顺序修正未另跑第三次完整 VAD。
- 本次临时广告牌 actor 4383 已删除，可重新生成；没有删除用户数据集。

复验工具：`python3 tools/validate_capture_dataset.py <capture目录>`；ROS 环境 source 后 `python3 tools/validate_sensor_wall.py`（需活跃闭环输入，30 秒超时）。

本次前端遵循项目已有 Sites 构建规范，但所有仿真、模型和数据仍在本机，没有部署云端。

## 尚需继续的工作

1. 非车辆真实网格、各材质槽 UV 及材质投影参数的通用 Unreal 导出，才能恢复准确的离线 3D 草稿编辑；目前是如实标记并提供实景验证，不是已解决所有资产 UV 映射。
2. 单独自然语言场景录制统一到新版多模态格式，以及其他模型新增采集的完整回归。
3. 长时间录制性能、ROS 完整 TF/轨迹发布、语义 BEV/未来轨迹真值，均不在本轮已验证功能内。

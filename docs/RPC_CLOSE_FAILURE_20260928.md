# 新发现的原生 RPC 关闭异常

历史快照网页验收前，页面出现 HTTP 503；只读预检 ready=false。

## 已核实证据

- 原 CARLA PID 56361 仍存在，进程状态 Ssl、主线程等待 do_sys_pause。进程存在不等于服务可用。
- 独立 `simulator_probe_worker` 在 get_server_version 等待 1000 ms 后超时。
- 引擎日志 2026-09-28 14:35:43 UTC 报 `Exception thrown: close: Bad file descriptor`，随后 SIGSEGV/StaticShutdownAfterError。
- 原生栈经过 `rpc::detail::server_session::close()` 的 lambda、ASIO socket.close、carla::throw_exception；不是此前渲染代理的崩溃栈。
- 最近对象清理记录在 14:32:18 UTC，约三分钟后才报此错；本次没有换图。不能据时序证明健康探测或对象删除是触发原因。
- 完整日志副本：`runs/validation/rpc-close-fatal-20260928.log`。
- 本地 Build 下目前找到 rpclib 的 libcxx/libstdcxx 安装头文件，未找到 server_session 实现源码；后续需要定位构建来源。

## 结论与后续

历史快照浏览器验收未完成，不能记录通过。当前原生服务已进入致命错误处理但进程未退出；未擅自把它当作正常服务，也未重启掩盖日志。

下一步定位实际 rpclib 构建来源及关闭路径的并发/重复关闭处理，验证能否使用不抛异常的错误码关闭并保留诊断；需要原生重建与连接/断连压力验收才能证明修复。隔离健康探测保护了桥接，但不能证明原生服务器不受连接生命周期问题影响。

## 源码定位与候选补丁

`Util/BuildTools/Setup.sh` 指定官方 `carla-simulator/rpclib` 的 `carla-callbacks` 分支。本次获取提交 `f7e1d73ebe3a2676b1fe46453e32e6aa71be35cf`。当前分支源码不等于已证明安装库由同一提交构建；仍需核对 ABI/头文件与重建链。

源码有三条关闭路径：server_session::close 的写 strand、do_read 末尾直接 close，以及 async_writer 的写完成回调。候选补丁 `integration/carla/rpclib-close-error-code.patch` 将读退出交给已有 close 队列，并将两处直接关闭改成 error_code 重载，记录非零错误而不进入 ASIO 抛异常路径。尚未证明全部 socket 并发访问安全，也未部署到 CARLA。

隔离源码 `/tmp/safeagent-rpclib-close-review`，构建 `/tmp/safeagent-rpclib-close-build`。此处默认 GNU/libstdc++ 编译仅验证候选源码，不可直接替换 Unreal libc++ 插件依赖；生产链接库由 Carla.Build.cs 指向 CarlaDependencies/lib/librpc.a。

## 隔离连接压力结果

候选库 GNU/libstdc++ 编译通过。`integration/carla/rpclib_connection_stress.cpp` 在独立 127.0.0.1:28765 上使用四工作线程，完成 2000 次创建客户端/真实 ping RPC/销毁客户端，另做 2000 次无 RPC 内容的 EOF/reset 连接断开；最后 ping 仍可用。输出 `rpc_calls=2000 errors=0`，退出 0，45 秒外部超时未触发。未连接 CARLA，未部署原生修复；没有未修改库对照实验，因此不能声称已复现并消除原故障。

安装版 server_session.h 与本次源码逐字节一致；其余依赖 ABI 和 Unreal libc++ 重建仍待完成。补丁存档发现终端噪声及结尾上下文缺失，已修正并重新校验。

## Unreal 工具链构建

已在 `/tmp/safeagent-rpclib-close-libcxx-build` 使用本机 Build/clang.sh、clang++.sh（Clang 10.0.1）、Unreal LibCxx include/lib、v17 sysroot 及 Setup.sh 的 BOOST_NO_EXCEPTIONS/ASIO_NO_EXCEPTIONS 参数成功构建候选静态库。

- 候选 SHA-256：`88d769830efca5843bd636a16dfd4144a7038b945a15ac7a2dfa8ba551e0a4fb`。
- 当前 Build libcxx 安装库及插件 CarlaDependencies/lib/librpc.a 均为 `ae8069508fa33b7a7cc5d09694a3bffe0496d50a7a16b14143471da9d223f468`。
- 编译有上游警告（未知 warning 开关、host include 与 sysroot 混用、旧 libc++ 保留宏），不是零警告构建；参数按本机现有 Setup.sh 核对。
- 候选保留 ASIO throw_exception 外部引用，其他异常路径仍可能致命；修复范围仅为选定 close 路径。
- 尚未覆盖安装库/头文件、未重链接 Unreal 插件、未恢复原生服务。async_writer 是头文件实现，部署必须同步相关头文件并确保依赖重编，不能仅替换 librpc.a 宣称完成。

## 部署增量（替代上述未部署状态）

通过精确哈希校验后，已备份并替换 Build libcxx 与插件 CarlaDependencies 两处 librpc.a/async_writer.h；四文件原件及哈希收据在 `runs/validation/rpc-install-c4b6371222a0479782184af4cdf5a726`。Unreal Build.sh CarlaUE4Editor Linux Development 成功完成 9 个链接/目标动作（7.19 秒），包含 libUE4Editor-Carla.so；输出没有 C++ 重编动作，不将其描述为全源码干净重编。

故障 PID 56361 收到 SIGTERM 后仍卡在 futex，精确复核 exe/项目命令后 SIGKILL 结束；原日志已提前保存。新实例按原 Town04 可视化参数启动，工具会话 68192。启动与真实 CARLA 连接压力验收仍在进行，不将独立库压力测试当作引擎验收。

## 实际服务恢复与定向验证

原桥接随后确认退出（工具返回 143，不能据此认定 Python/native crash），重新启动桥接后完整 preflight ready=true、Town04、synchronous=false。独立模拟器 RPC 始终可再次查询。

新增 `tools/regression_carla_rpc_disconnect.py` 对真实 CARLA 执行四线程 200 次独立进程版本 RPC 与 EOF/reset 连断，结束再做一次，两类各 201 次；3.47 秒完成、最后 RPC 正常、本次日志增量无 fatal/critical/unhandled exception。收据 `runs/validation/carla-rpc-disconnect-d01394679d6549e5a11d5ea6179fbe94.json`。前端、桥接与新 CARLA 保持运行。

此项是候选补丁部署后的短定向通过，不是原故障稳定复现后的 A/B 消除证明，也不是长时间轮询、场景编辑、传感器或模型全矩阵验收；故障仍待延长测试后关闭。

持续测试增量：脚本加入 0..600 秒时长参数和探测失败收据。真实 CARLA `--duration 60` 四线程连续 18 轮，61.58 秒完成 3601 组版本 RPC/EOF-reset 断连，最终查询正常、增量日志无致命错误。收据 `runs/validation/carla-rpc-disconnect-b746f0d825b94c13a30d480a3b2bcf28.json`。一分钟连断不是长路线或所有崩溃矩阵通过。同期前端生产构建与恢复请求不重试契约测试通过，保留 vinext Unknown 路由分类提示。

传感器实机增量：部署候选后执行 `regression_sensor_rig.py --mode autopilot`，120 帧/40 同步样本，位移 36.099 米，RGB 原始输入、米制深度、XYZI、BEV、14/14 外参、归档地图与时间索引验证通过；重复启动拒绝，cleanup_errors=[]。退出观察 5 秒/21 次，保持异步、零传感器、帧持续推进。录制 `capture-20260928T230312-279d7e8a`，收据 `runs/validation/sensor-rig-5a96992c914a48f1985d65a65999d4ad.json`。保留 client/server dirty 后缀警告；这是真实规则采集，不是端到端模型回归。

# 本机项目包界面

在“项目与场景版本”中选择已保存场景，下方“项目包”可以导出全部保存版本及引用纹理，可选包含引用材质的真实网格预览。ZIP 下载后可上传校验，并在勾选确认后隔离导入。

- 浏览器上传上限16 MiB；项目包解压总量沿用256 MiB限制。更大的上传及手动源包绑定仍使用 `tools/project_bundle.py` 的CLI流程。图形导出不等于完整系统备份。
- 服务接受场景/包ID、显式包含标志及可选模型引用JSON，不接受任意本机源路径、目标目录或下载文件名。操作互斥，拒绝重定向的包目录和隔离导入目录。
- 上传先验证条目、路径、校验和与依赖清单，之后才暂存；导入创建 `data/imported-projects/carla-project-*` 新目录，不覆盖活动场景目录，不加载CARLA、不执行脚本、不注册Unreal资产。
- “文件校验通过”不等于“本机依赖可用”。权重、数据集、源代码不在此场景包内；包中的源资产也需要明确导入Unreal。
- 操作失败不自动重试写入。中断的partial包不会作为完成ZIP提供下载；保留失败文件供排查。当前图形界面没有跨机环境安装、导入历史列表或整套资产注册向导。

接口：POST `/projects/bundle/export`、`upload`、`import`；GET `/projects/bundle?bundle_id=...` 和 `/projects/bundle/download?bundle_id=...`。上传为ZIP原始字节；隔离导入要求 `confirmed:true`。

本机依赖检查：POST `/projects/bundle/doctor` 只接收bundle_id。拒绝活跃仿真任务，观察已安装地图、原生Blueprint和当前地图的精确材质预览依赖，不切换地图、不生成对象。返回观察时间及字符串episode防止浏览器丢失64位精度；可用/缺失/未检查分开显示。生成资产别名、模型文件、非当前地图材质仍保留未检查状态。它检查当前工作台，不代表隔离导入目录已经配置Python/CUDA环境。

依赖界面回环browser-models-2347750e-824f-4630-8ca6-24be58c95846通过；原生前后episode、地图、对象集合一致，5秒健康观察持续异步且无传感器，详见同目录dependency-verification.json。最终状态文案回归browser-models-1a419366-973a-4727-b588-7c6f6202087e通过。589项Python测试、类型检查和构建通过。

实测：浏览器空场景回环通过（browser-models-7bf1ae18-5073-4278-9713-6ffbd35acf04）。含两个版本、真实纹理、真实材质预览的6文件回环通过（browser-models-5ac57a20-be45-4892-8227-359d71e07767），截图已查看；`verify_browser_bundle.py --require-material-preview` 比较导出/上传包字节、全部隔离文件及当前场景版本，均一致。隔离目录carla-project-w0mqwrie保留，不代表已在另一台机器验证运行。

## 图形源资产与模型引用增量

导出可勾选include_generated_sources，覆盖已选场景所有保存版本引用的generated.prop别名；依据本机注册表只读取.runtime/blender-assets内直接任务目录的asset.fbx/asset.blend/asset.glb/texture.png及明确颜色/粗糙度。缺失来源、旧目录、软链接或不明确参数拒绝最终ZIP，不悄悄漏包。场景先形成不可变快照，再绑定来源，不因打包期间场景变化混合新旧版本。中间快照/source目录保留；不自动清理失败证据，不宣称跨文件资产读取为数据库事务。

可选择carla-runtime-reference/1 JSON（1 MiB以内）附加模型文件别名路径、大小及SHA256；导出校验结构，不重新读取权重，也不保证引用与当前模型文件一致。引用校验与运行环境安装仍须另外执行。此操作不执行FBX、blend、配置或模型权重。

629项Python测试、类型及生产构建通过。真实浏览器81d28d76-9487-4a97-b297-dd35abfe04d8完成源资产+五模型引用的5文件导出/上传/确认隔离导入，截图已查看；源包每个文件与本机原件、材质参数、引用JSON、所有隔离文件均匹配。目录carla-project-jhmp6ecq；只读依赖检查前后世界身份/对象不变且健康观察通过。未自动在Unreal注册、未恢复实景，跨机运行仍未验证。

补充严格布尔标志测试后630项通过；既有两版本纹理/预览回环3c719b40-d593-4e20-bce1-15f555c458d3通过，6文件逐一验证、活动场景版本不变，隔离目录carla-project-q1nlr2dz。

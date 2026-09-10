# 本机项目包界面

在“项目与场景版本”中选择已保存场景，下方“项目包”可以导出全部保存版本及引用纹理，可选包含引用材质的真实网格预览。ZIP 下载后可上传校验，并在勾选确认后隔离导入。

- 浏览器上传上限16 MiB；项目包解压总量沿用256 MiB限制。更大的上传、生成资产源包绑定、模型文件引用使用 `tools/project_bundle.py` 的现有CLI流程。图形导出不等于完整系统备份。
- 服务仅接受场景/包ID，不接受任意源路径、目标目录或下载文件名。操作互斥，拒绝重定向的包目录和隔离导入目录。
- 上传先验证条目、路径、校验和与依赖清单，之后才暂存；导入创建 `data/imported-projects/carla-project-*` 新目录，不覆盖活动场景目录，不加载CARLA、不执行脚本、不注册Unreal资产。
- “文件校验通过”不等于“本机依赖可用”。权重、数据集、源代码不在此场景包内；包中的源资产也需要明确导入Unreal。
- 操作失败不自动重试写入。中断的partial包不会作为完成ZIP提供下载；保留失败文件供排查。当前图形界面没有跨机环境安装、导入历史列表或整套资产注册向导。

接口：POST `/projects/bundle/export`、`upload`、`import`；GET `/projects/bundle?bundle_id=...` 和 `/projects/bundle/download?bundle_id=...`。上传为ZIP原始字节；隔离导入要求 `confirmed:true`。

实测：浏览器空场景回环通过（browser-models-7bf1ae18-5073-4278-9713-6ffbd35acf04）。含两个版本、真实纹理、真实材质预览的6文件回环通过（browser-models-5ac57a20-be45-4892-8227-359d71e07767），截图已查看；`verify_browser_bundle.py --require-material-preview` 比较导出/上传包字节、全部隔离文件及当前场景版本，均一致。隔离目录carla-project-w0mqwrie保留，不代表已在另一台机器验证运行。

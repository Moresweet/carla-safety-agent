# 可校验的源码迁移快照

源码包与场景包分开：源码包保存已提交程序/测试/文档/ROS工具/引擎补丁；
场景包保存场景版本、纹理和显式选择的 Blender 源资产。两者均不包含运行环境或模型权重。

```bash
PYTHONPATH=src python3 tools/source_bundle.py export --project . --output /explicit/path/source.zip
PYTHONPATH=src python3 tools/source_bundle.py verify /explicit/path/source.zip
PYTHONPATH=src python3 tools/source_bundle.py restore /explicit/path/source.zip --destination /explicit/path/new-source
```

导出锁定一个准确 HEAD commit，并从 Git 对象读取文件，不读取未提交工作副本。
因此未提交/未跟踪文件不会进入源码包。每个文件记录 SHA-256、大小和Unix权限，
压缩包保留脚本可执行位；校验只验证包内字节与结构，不执行程序、不安装依赖。
Git命令均为本地读取，不访问远程。内容校验和不是来源签名或安全审计。

纳入根README、pyproject.toml、.gitignore，以及src/tools/scripts/tests/docs/integration/ros2/schema。
排除.git、运行数据、node_modules、构建目录、.env、常见私钥和权重/编译资产扩展名。
不纳入本机Codex/托管配置。筛选不是通用秘密扫描；对外分享前仍需检查源码内容，
尤其是历史提交本身可能含有的硬编码敏感信息。

限5000文件、单文件32MiB、源字节256MiB；拒绝选中源码中的符号链接、子模块和未解析LFS指针。
输出不覆盖已有文件，临时包校验通过才以不覆盖方式发布；失败保留partial文件供检查。
发布后磁盘同步失败可能同时留下完整目标和partial，不能盲目重试或宣称全回滚。

restore命令先完整校验同一份有界内存快照，再写入全新目录；已有目录（即使为空）拒绝。
恢复文件权限，写入SOURCE_RESTORE_RECEIPT.json，但不恢复.git历史、不运行任何脚本。
失败保留部分恢复目录并报告路径，不自动删除或覆盖。新归档记录遗漏的未提交源文件名，
恢复回执保留警告；旧归档未记录时返回未知，不推断为无遗漏。

目标机使用上述恢复命令后，依据PROJECT_MIGRATION.md配置路径、安装依赖并应用/编译
对应引擎补丁；再处理场景包、资产注册与模型文件引用。解压不等于环境已就绪。
当前没有自动执行安装脚本或在目标机器验收，避免把“包完整”误当成“可以直接运行”。

源码测试覆盖提交与脏文件隔离、排除项、权限、已有输出保护、篡改与符号链接拒绝、
遗漏清单兼容、API及CLI恢复往返。仍需目标机器的完整环境和功能验收。
# 最新开发状态检查

迁移当前开发成果时使用 `PYTHONPATH=src python3 tools/source_bundle.py export --project . --output /绝对路径/source.zip --require-current`。
该选项仍只导出已提交源码：发现选定源码有未提交修改、删除或新增文件会拒绝，必须先审查并提交需要交付的源码。
写出临时包并校验后、发布最终ZIP前，再核对HEAD和源码改动；期间变化则拒绝发布并保留partial供检查。
这不是对编辑器/Git的全局锁，不能承诺任意并发编辑下的原子工作树快照；导出期间应暂停源码编辑。
权重、运行数据、环境和引擎二进制仍不包含。普通历史提交快照可不加该选项，但不可冒充最新开发备份。
# 当前源码导出就绪检查

运行 `PYTHONPATH=src python3 tools/source_bundle.py status --project .`，只读返回HEAD和源码导出会遗漏的未提交路径，不暂存、不提交、不导出。`current_source_export_ready`仅表示选定源码与提交一致，不表示依赖、runtime数据或跨机环境已就绪。

2026-09-29核对HEAD为e1651f7037962b724e3219a37efd1c4eef79dec6，当时有320个选定源码路径未提交，包含最新容量、材质历史和批量报告改动；因此旧式默认导出不代表当前开发备份。交付当前版本应先审核并提交所需源码，再使用export的`--require-current`门禁。不要以默认旧版本包替代当前交付。新增状态检查及源码包专项34项通过（0.53秒），检查不改变Git索引。最新GitHub推送仍未完成。

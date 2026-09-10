# 可校验的源码迁移快照

源码包与场景包分开：源码包保存已提交程序/测试/文档/ROS工具/引擎补丁；
场景包保存场景版本、纹理和显式选择的 Blender 源资产。两者均不包含运行环境或模型权重。

```bash
PYTHONPATH=src python3 tools/source_bundle.py export --project . --output /explicit/path/source.zip
PYTHONPATH=src python3 tools/source_bundle.py verify /explicit/path/source.zip
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

目标机先校验再解压到新目录，依据PROJECT_MIGRATION.md配置路径、安装依赖并应用/编译
对应引擎补丁；再处理场景包、资产注册与模型文件引用。解压不等于环境已就绪。
当前没有自动执行安装脚本或在目标机器验收，避免把“包完整”误当成“可以直接运行”。

17项源码快照测试覆盖提交与脏文件隔离、排除项、权限、已有输出保护、篡改与符号链接拒绝。

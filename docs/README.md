# Cloudra 文档

[English](README_EN.md) · [项目首页](../README_CN.md)

第一次使用，从[安装与桌面启动](INSTALL_CN.md)开始；原生 Windows 用户使用 [`windows` 分支教程](https://github.com/yyywaa/Cloudra-mechanism-agent/blob/windows/docs/INSTALL_WINDOWS_CN.md)。核查论文实验结果或复现图表，从[论文、数据与复现](RESEARCH_DATA_CN.md)开始；预印本见 [arXiv:2611.02909](https://arxiv.org/abs/2611.02909)。

## 使用与理解结果

| 文档 | 你可以在这里找到 |
| --- | --- |
| [安装与桌面启动](INSTALL_CN.md) | 下载 macOS / Linux 安装包、桌面启动、首次配置；另附源码安装。 |
| [配置指南](CONFIGURATION_CN.md) | 模型登录、联网搜索、对话命令与服务访问。 |
| [分子工作台](MOLECULAR_WORKBENCH_CN.md) | 结构、计算与机理页面；逐帧查看、分子编辑、冻结／扫描、共享基团与保存。 |
| [混合溶剂建盒](MD_BOX.md) | 周期盒、初始密度检查和溶剂参考数据维护。 |
| [TS 流程与科学验收](TS_PROCESS_SOP.md) | 过渡态搜索、修订、停止以及频率和 IRC 证据要求。 |
| [DAG 编排](DAG_ORCHESTRATION.md) | 三种模式、机理图、证据绑定与 Supervisor 审查。 |
| [论文、数据与复现](RESEARCH_DATA_CN.md) | 图表复算、原始实验、Gold 与重新运行的不同入口。 |

## 部署与配置

- [SSH 远端计算](../deploy/ssh_remote_node.md)：Cloudra 在本机运行，量化计算提交到远端。
- [HPC / Slurm 部署](../deploy/hpc_cluster_deployment.md)：集群部署、环境准备和操作示例。
- [节点注册表](NODE_REGISTRY.md)：节点配置、工作区路由及执行语义。
- [MACE / ORCA 外部势配置](../deploy/mace_omol25_orca_external_setup.md)、[macOS xTB-IFF 适配](../deploy/xtbiff_macos_shim.md)：特定工具环境。

## 参与开发

从[贡献指南](../CONTRIBUTING.md)了解开发检查与提交方式；[AGENTS.md](../AGENTS.md)维护协作规则。

| 文档 | 内容 |
| --- | --- |
| [架构与目录地图](ARCHITECTURE.md) | Agent 内核、计算调度、数据存储及模块职责。 |
| [工具调用协议](TOOL_PROTOCOLS.md) | JavaScript / traditional 协议、工具文档加载与运行边界。 |
| [运行观测](RUNTIME_OBSERVABILITY.md) | Agent 活动、完整工具回执与计算关联 API。 |
| [插件开发](PLUGINS.md) | 插件接口、事件与知识检索。 |
| [知识标签](KNOWLEDGE_TAGS.md) | 知识库标签约定。 |
| [IDPP 路径模式](IDPP_MODES.md) | 路径模式、数值停止和证据语义。 |
| [脚本索引](../scripts/README.md) | 运行与数据维护脚本。 |
| [许可证与第三方归属](licenses/README.md) | 项目及第三方组件的许可信息。 |

## 历史记录

已完成的计划、旧设计和验收过程留在 `docs/archive/`、`docs/superpowers/`、`gold_compute/archive/` 与 `ideapool/archive/`，供需要时追溯。旧稿件及其编辑产物保留在 Git 历史中，当前分支提供实验数据与复现代码。历史材料不代替上面的当前指南，也不构成新的待算任务。版本变化见 [CHANGELOG](../CHANGELOG.md)。

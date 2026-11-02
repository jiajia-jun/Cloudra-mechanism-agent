# 论文、数据与复现

[English](RESEARCH_DATA.md) · [返回文档中心](README.md)

当前论文题目为 **Cloudra: Geometric Reasoning and Scientific Validation for Autonomous Reaction Mechanism Exploration**，已提交 arXiv，等待公告。[中英文主稿与 SI](../paper/overleaf/README.md)是论文源文件入口。

## 按目的选择入口

| 你想做什么 | 从哪里开始 | 需要什么 |
| --- | --- | --- |
| 复现论文表格和图件 | [SI 配套复现包](benchmarks/P2_DELIVERY.md#si-配套复现包)，解压后阅读 `companion_data/` 中的说明 | 使用包内数据与分析脚本，不重新运行 Agent 或量化计算。 |
| 检查正式实验的研究轨迹与原生日志 | [P2 完整归档](benchmarks/P2_DELIVERY.md) | 50 题 × 四种配置，共 200 次保留运行；14.9 GB 完整包已公开只读。 |
| 检查先导重复实验 | [P1b 数据包](benchmarks/P1B_DELIVERY.md) | 48 次运行，原始记录、历史重评分与 Standard 离线整理分别保存。 |
| 检查行为分析和激活干预 | [第三章完整原始档案](benchmarks/P2_DELIVERY.md#行为实验与激活原始档案) | 原始档案与精简 SI 包配套使用。 |
| 审查或重跑 Gold 参考计算 | [Gold 下载与复现](../gold_compute/evidence/REPRODUCE.md)及[逐题索引](../gold_compute/evidence/README.md) | 回读原件不提交计算；重新运行需要对应引擎与资源，方法和依赖以原输入为准。 |
| 重新运行 Agent Benchmark | [Benchmark 运行指南](../cloudra/benchmark/README.md) | 需要模型、计算节点及量化软件，会产生新的模型与计算开销。 |

各数据包集中在[公开研究数据目录](https://drive.google.com/drive/folders/1yZo3eJuCUuAgedQztgCtLyJcc8MZipf7)。版本、文件名、校验值、权限及上传进度以各包交付页为准。

## 怎样理解发布结果

正式评分来自对每次运行已有记录的离线整理：可以恢复缺失的图文件、修复文件引用、换算已有数值；不得新增原运行没有的科学结论或计算证据。运行时是否交付图、离线评分和科学验证状态分别记录。评分定义见[Benchmark 说明](../cloudra/benchmark/README.md)。

Gold 的原件缺失、真实 IRC 来源限制及人工验收例外见[当前参考状态](../gold_compute/queue_20261018/REFERENCE_STATUS.md)。数据可下载或校验通过，不表示全部参考反应已有完整的独立复现证据。

## 版本与引用

检查已发布结果时使用对应数据包记录的代码快照。重新运行时记录所用提交、模型与计算设置；当前分支可能已经包含后续开发改动。

论文引用见根目录 [CITATION.bib](../CITATION.bib)，GitHub 引用信息见 [CITATION.cff](../CITATION.cff)。arXiv 编号将在论文正式发布后补充。

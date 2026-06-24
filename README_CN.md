# Cloudra

专为化学科研设计的 AI Agent 协作框架。

## 核心亮点

- **自研 ReAct 框架**：不依赖 LangChain、AutoGPT 等重型框架，拥有完全可控的轻量级推理-行动循环，适合需要可追溯性的科研场景。
- **人机协同闭环**：高危/脚本操作强制进入人工审批流；Agent 可通过 `ask_user` 主动暂停任务、向用户澄清需求。
- **化学工具齐全**：覆盖分子绘图、图片转 SMILES、NMR/IR 原始数据处理、Gaussian 输入生成、格式转换、输出日志解析、DFT 任务提交与监控。
- **多进程安全架构**：Coordinator 与 Follower 在独立进程中运行，基于 SQLite WAL、位标志权限和审批日志保障安全。

## 安装

```bash
pip install -e .
```

需要 Python 3.10+。

## 快速开始

初始化配置：

```bash
cloudra config init
```

运行任务：

```bash
cloudra run "搜索钙钛矿太阳能电池最新论文并总结关键发现"
```

继续上次对话：

```bash
cloudra run "继续之前的分析"
```

## CLI 命令参考

```bash
# 顶层选项
cloudra --version
cloudra --coordinator-model gpt-4o --coordinator-key $KEY run "..."

# 运行任务
cloudra run "你的任务"                  # 启动或自动恢复上次对话
cloudra run "你的任务" --new            # 强制新建对话
cloudra run "你的任务" --conv-id ID     # 继续指定对话
cloudra run "你的任务" --dry-run        # 只打印配置，不执行

# 配置管理
cloudra config init                     # 交互式初始化
cloudra config show                     # 查看当前配置（敏感信息脱敏）
cloudra config get coordinator.model
cloudra config set follower.model gpt-4o

# 状态查看
cloudra history                         # 历史对话列表
cloudra logs CONV_ID                    # 查看某对话日志
cloudra sessions                        # Session 状态
cloudra skills                          # 可用 Skills

# 远程邮件唤醒
python -m cloudra.email_listener
```

## 计算化学工作流示例

```bash
# 1. 生成 Gaussian 输入文件
cloudra run "为苯分子生成 B3LYP/6-31g(d) 的 gjf，保存到 /tmp/benzene.gjf"

# 2. 提交计算任务（同步阻塞或异步后台）
cloudra run "提交 /tmp/benzene.gjf 作为 Gaussian 任务并等待完成"

# 3. 解析输出
cloudra run "解析 /tmp/benzene.out，报告 SCF 能量、HOMO-LUMO 能隙和振动频率"
```

## 工具一览

| 类别 | 工具 |
| :--- | :--- |
| 化学工具 | `gjf_writer`、`gaussian_log_parser`、`format_converter`、`molecule_drawer`、`image_to_smiles`、`smiles_to_mol`、`nmr_processor`、`ir_processor` |
| 文献检索 | `paper_searcher`、`chemrxiv_searcher`、`pdf2md`、`text_reader`、`image_reader`、`web_fetcher`、`headless_browser` |
| 执行协作 | `bashtools`、`text_writer`、`subagent_launcher`、`submit_compute_job` |
| 人机交互 | `ask_user`、`email_sender`、`email_reader` |
| 流程控制 | `stop`、`getskill`、`get_subagent_report` |

## 安全模型

Cloudra 使用位标志权限（`READ`、`WRITE`、`SCRIPT`、`DESTRUCTIVE`、`MANAGE`）。危险操作会被挂起并写入 `approvals` 表，等待用户在 CLI/API 中显式通过或驳回。

## 许可证

详见 [copyright_docs/](copyright_docs/)。

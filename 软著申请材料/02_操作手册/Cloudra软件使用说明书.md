# Cloudra 软件使用说明书

## 一、软件概述

### 1.1 软件名称
**Cloudra（agent4chem）**

### 1.2 软件版本
**V1.6.2**

### 1.3 开发完成日期
2026 年 7 月

### 1.4 软件用途
Cloudra 是一款面向化学科研领域的 AI Agent 协作框架软件。它通过协调多个专业化智能代理（Agent），为化学研究人员提供文献检索、数据分析、化学结构处理、光谱数据解析、DFT 计算任务提交与监控、远程邮件交互及代码执行等一站式科研辅助服务。

### 1.5 运行环境
- **操作系统**：Linux、macOS、Windows
- **Python 版本**：Python 3.10 及以上
- **依赖环境**：OpenAI 兼容的大语言模型 API、IMAP/SMTP 邮件服务（可选）

---

## 二、软件功能模块

### 2.1 核心架构模块

#### 2.1.1 多进程管理架构
软件采用 Coordinator-Follower 多进程模型：
- **Coordinator（协调者）**：中央管理器，接收用户需求，拆解任务并分发给子 Agent。
- **Follower（追随者）**：多个独立工作进程，执行被分配的子任务。
- 各 Agent 运行在独立进程中，确保任务隔离与系统稳定性。

#### 2.1.2 ReAct 推理引擎
实现 Thought → Action → Observation 循环：
- **推理阶段（Thought）**：Agent 分析上下文和可用工具，决定下一步行动。
- **行动阶段（Action）**：通过工具执行引擎调用外部能力。
- **观察阶段（Observation）**：读取工具返回结果，评估是否符合预期。
- 支持人机交互闭环（Ask User），在关键节点征求用户意见。

#### 2.1.3 上下文管理
- **统一上下文渲染**：`ContextManager` 负责消息构建、图片 base64 编码、视觉降级与视觉历史窗口。
- **上下文压缩**：当上下文超过模型窗口一半时，自动对较早历史生成摘要，防止无限增长。
- **多会话隔离**：每个对话拥有独立的上下文文件与数据库记录。

#### 2.1.4 远程控制与自动唤醒模块
- **邮件监听服务（Email Listener）**：后台静默运行，自动监听指定邮箱。
- **指令识别**：识别带有 `CLOUDRA:` 前缀的邮件，自动触发 AI 任务。
- **安全白名单**：仅响应授权列表中的发件人，确保系统安全。

### 2.2 专业化 Agent 矩阵

| Agent 名称 | 标识 | 功能定位 |
|-----------|------|---------|
| Coordinator | a-0 | 任务协调与总控 |
| Explorer | a-1 | 项目文件结构导航与发现 |
| Writer | a-2 | 文档撰写、报告总结、代码编写 |
| Researcher | a-3 | 学术文献检索与专业数据调研 |
| Visionary | a-4 | 视觉识别、原始实验图谱解析 |
| Operator | a-5 | 系统环境管理、高风险操作执行 |
| Coder | a-6 | 科学计算流水线开发、算法实现 |

### 2.3 工具套件（Tools）

#### 2.3.1 化学与计算工具
- **化学结构识别（Image to SMILES）**：基于 DECIMER 深度学习模型，将化学结构图转换为 SMILES 字符串。
- **光谱处理套件（Spectroscopy Suite）**：包含 NMRProcessor 和 IRProcessor，支持 Bruker、JCAMP-DX 等格式的原始波谱处理、相位校正及峰识别。
- **DFT 计算辅助**：Gaussian 输入生成、输出日志解析、计算任务提交与监控。
- **分子可视化**：基于 RDKit 的分子结构 2D 渲染与格式转换。

#### 2.3.2 交互与通讯工具
- **远程邮件发送/读取**：Agent 可自动发送实验进展报告至用户邮箱，或读取收件箱中的后续指令。
- **用户问答工具（Ask User）**：支持 Agent 主动发起多轮对话，用于澄清复杂需求或获取关键实验参数。

#### 2.3.3 搜索与阅读工具
- **专业文献搜索**：支持 arXiv、ChemRxiv 学术数据库。
- **多模态阅读器**：支持 PDF 转 Markdown、图片 OCR 及结构化文本提取。

#### 2.3.4 管理与知识工具
- **子 Agent 调度**：动态管理子进程生命周期。
- **领域知识库（Skill System）**：允许用户通过编写 Markdown 文档扩展 Agent 的领域知识。

#### 2.3.5 系统工具
- **跨平台 Bash 工具**：针对 Windows/Linux 优化，支持指令集自动识别与路径回退。
- **文本持久化**：结构化实验记录与报告写入。

### 2.4 安全与权限系统

#### 2.4.1 五级权限模型
- **READ（读取权限）**：读取文件和数据
- **WRITE（写入权限）**：写入文件
- **MANAGE（管理权限）**：启动子 Agent
- **SCRIPT（脚本权限）**：执行脚本
- **DESTRUCTIVE（破坏权限）**：执行危险操作（如删除文件）

#### 2.4.2 危险操作审批流
- 默认模式下，危险操作触发人工审批流程，等待用户确认。
- **YOLO 模式**：通过 `--yolo` 标志启用，由独立 LLM Guard 自动审批危险操作，适用于可信的自动化环境。

### 2.5 数据管理
- **SQLite 持久化**：对话、审批、计算任务均写入 SQLite，支持 WAL 模式。
- **API 服务**：内置基于 FastAPI 的本地 API 接口，支持移动端和 Web 端接入。

---

## 三、软件安装与配置

### 3.1 安装步骤

```bash
# 克隆代码仓库
git clone https://github.com/cloudra/agent4chem
cd agent4chem

# 安装软件（依赖统一声明在 pyproject.toml）
pip install -e .
```

### 3.2 初始化配置

```bash
cloudra config init
```

交互式配置以下内容：
- Coordinator 模型信息
- Follower 模型信息
- 邮件服务配置（IMAP/SMTP）及安全白名单

### 3.3 启动 API 服务

```bash
python -m cloudra.api
```

服务默认监听 `0.0.0.0:8000`，静态文件通过 `/data` 路径访问。

### 3.4 启动远程唤醒服务

```bash
python -m cloudra.email_listener
```

---

## 四、软件使用方法

### 4.1 运行科研任务

```bash
# 普通模式
cloudra run "搜索钙钛矿太阳能电池最新论文并总结"

# 强制新建对话
cloudra run "搜索钙钛矿太阳能电池最新论文并总结" --new

# 指定对话 ID 继续
cloudra run "继续分析" --conv-id <CONV_ID>

# 仅查看配置，不执行
cloudra run "搜索钙钛矿太阳能电池最新论文并总结" --dry-run

# YOLO 全自动模式
cloudra run "批量处理 /tmp/data 下所有光谱" --yolo
```

### 4.2 常用管理指令

- `cloudra --version`：查看版本
- `cloudra history`：查看历史对话
- `cloudra logs [对话ID]`：查看 Agent 推理日志
- `cloudra sessions`：查看当前活跃会话
- `cloudra skills`：查看已加载的领域知识库
- `cloudra config show`：查看当前系统配置
- `cloudra config get coordinator.model`：读取配置项
- `cloudra config set follower.model gpt-4o`：设置配置项

### 4.3 计算化学工作流示例

```bash
# 1. 生成 Gaussian 输入文件
cloudra run "为苯分子生成 B3LYP/6-31g(d) 的 gjf，保存到 /tmp/benzene.gjf"

# 2. 提交计算任务
cloudra run "提交 /tmp/benzene.gjf 作为 Gaussian 任务并等待完成"

# 3. 解析输出
cloudra run "解析 /tmp/benzene.out，报告 SCF 能量、HOMO-LUMO 能隙和振动频率"
```

---

## 五、典型使用场景

### 5.1 远程指令触发
用户在外出时通过邮件发送 `CLOUDRA: 调研 MOF 材料最新合成方法`，系统自动被唤醒并开始工作，完成后将报告回复至用户邮箱。

### 5.2 复杂光谱解析
用户上传包含原始 Bruker 数据的文件夹，Agent 自动识别并调用 NMRProcessor 进行傅里叶变换和峰识别，产出标准的峰表报告。

### 5.3 DFT 计算全流程辅助
Agent 协助用户选择泛函与基组（通过 Skill 系统），在计算完成后调用日志解析工具自动提取 SCF 能量、HOMO-LUMO 能隙等关键指标。

---

## 六、技术支持

- **开发团队**：Cloudra Team

---

*本说明书适用于 Cloudra V1.6.2 版本*

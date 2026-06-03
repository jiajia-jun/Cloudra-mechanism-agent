# Cloudra 软件使用说明书

## 一、软件概述

### 1.1 软件名称
**Cloudra（agent4chem）**

### 1.2 软件版本
**V1.2.0**

### 1.3 开发完成日期
2026年6月

### 1.4 软件用途
Cloudra 是一款面向化学科研领域的 AI Agent 协作框架软件。它通过协调多个专业化智能代理（Agent），为化学研究人员提供文献检索、数据分析、化学结构处理、光谱数据解析、DFT 计算数据后处理、远程邮件交互及代码执行等一站式科研辅助服务。

### 1.5 运行环境
- **操作系统**：Linux、Windows (全面兼容)
- **Python 版本**：Python 3.10 及以上
- **依赖环境**：OpenAI API 兼容的大语言模型接口、IMAP/SMTP 邮件服务（可选）

---

## 二、软件功能模块

### 2.1 核心架构模块

#### 2.1.1 多进程管理架构
软件采用 Manager-Worker 多进程模型：
- **Coordinator（协调者）**：作为中央管理器，负责接收用户需求，拆解任务并分发给子 Agent。
- **Follower（追随者）**：多个独立工作进程，各自执行被分配的子任务。
- 各 Agent 运行在独立进程中，确保任务执行的隔离性和系统稳定性。

#### 2.1.2 远程控制与自动唤醒模块
- **邮件监听服务（Email Listener）**：支持后台静默运行，自动监听指定邮箱。
- **指令识别**：识别带有特定前缀（如 `CLOUDRA:`）的邮件，自动触发 AI 任务。
- **安全白名单**：仅响应授权列表中的发件人，确保系统安全。

#### 2.1.3 ReAct 推理引擎
实现单循环 Reasoning-Acting（推理-行动）架构：
- **推理阶段（Reasoning）**：Agent 分析上下文和可用工具，决定下一步行动。
- **行动阶段（Acting）**：通过工具执行引擎（Executor）调用外部能力。
- 支持人机交互闭环（Ask User），在推理过程中实时征求用户意见。

### 2.2 专业化 Agent 矩阵

| Agent 名称 | 标识 | 功能定位 |
|-----------|------|---------|
| Coordinator | a-0 | 任务协调与总控 |
| Explorer | a-1 | 项目文件结构导航与发现 |
| Writer | a-2 | 文档撰写、报告总结 |
| Researcher | a-3 | 学术文献检索与专业数据调研 |
| Visionary | a-4 | 视觉识别、原始实验图谱解析 |
| Operator | a-5 | 系统环境管理、高风险操作执行 |
| Coder | a-6 | 科学计算流水线开发、算法实现 |

### 2.3 工具套件（Tools）

#### 2.3.1 化学与计算工具（Chemtool & Vaspkit）
- **化学结构识别（Image to SMILES）**：基于 DECIMER 深度学习模型，将化学结构图（截图、手绘图）转换为 SMILES 字符串。
- **光谱处理套件（Spectroscopy Suite）**：包含 NMRProcessor 和 IRProcessor，支持 Bruker、JCAMP-DX 等格式的原始波谱处理、相位校正及峰识别。
- **DFT 后处理（VASPKIT-Py Integration）**：集成 VASP 计算后处理功能，自动解析能带结构、态密度（DOS）和电荷密度数据并生成可视化图表。
- **分子可视化**：基于 RDKit 的分子结构 2D/3D 渲染。

#### 2.3.2 交互与通讯工具（Interactool）
- **远程邮件发送/读取**：Agent 可自动发送实验进展报告至用户邮箱，或读取收件箱中的后续指令。
- **用户问答工具（Ask User）**：支持 Agent 主动发起多轮对话，用于澄清复杂需求或获取关键实验参数。

#### 2.3.3 搜索与阅读工具（Searchtool）
- **专业文献搜索**：支持 ArXiv、ChemRxiv 学术数据库。
- **多模态阅读器**：支持 PDF 转 Markdown、图片 OCR 及结构化文本提取。

#### 2.3.4 管理与知识工具（Managetool & Skilltool）
- **子 Agent 调度**：动态管理子进程生命周期。
- **领域知识库（Skill System）**：允许用户通过编写 Markdown 文档扩展 Agent 的领域知识（如特定实验 SOP 或计算标准）。

#### 2.3.5 系统工具
- **跨平台 Bash 工具**：针对 Windows/Linux 优化，支持指令集自动识别与路径回退。
- **文本持久化**：结构化实验记录与报告写入。

### 2.4 安全与权限系统

#### 2.4.1 五级权限模型
- **READ（读取权限）**：读取文件和数据的权限
- **WRITE（写入权限）**：写入文件的权限
- **MANAGE（管理权限）**：启动子 Agent 的权限
- **SCRIPT（脚本权限）**：执行脚本的权限
- **DESTRUCTIVE（破坏权限）**：执行危险操作（如删除文件）的权限

#### 2.4.2 危险操作审批流
当 Agent 执行危险操作时，系统会触发人工审批流程，要求用户确认是否允许执行。

### 2.5 数据管理
- **上下文延迟加载**：优化大规模对话历史加载速度。
- **数据库增强**：支持 SQLite 并发锁定与乐观锁，提升多任务场景下的存储效率。
- **API 服务**：内置基于 FastAPI 的本地 API 接口，支持移动端和 Web 端接入。

---

## 三、软件安装与配置

### 3.1 安装步骤

```bash
# 克隆代码仓库
git clone https://github.com/cloudra/agent4chem
cd agent4chem

# 安装软件
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

### 3.3 远程唤醒服务启动

```bash
python -m cloudra.email_listener
```

---

## 四、软件使用方法

### 4.1 运行科研任务

```bash
cloudra run "搜索钙钛矿太阳能电池最新论文并总结"
```

### 4.2 常用管理指令

- `cloudra history`：查看历史对话
- `cloudra logs [对话ID]`：查看 Agent 推理日志
- `cloudra sessions`：查看当前活跃会话
- `cloudra skills`：查看已加载的领域知识库
- `cloudra config show`：查看当前系统配置

---

## 五、典型使用场景

### 5.1 远程指令触发
用户在外出时通过邮件发送 `CLOUDRA: 调研 MOF 材料最新合成方法`，系统自动被唤醒并开始工作，完成后将报告回复至用户邮箱。

### 5.2 复杂光谱解析
用户上传包含原始 Bruker 数据的文件夹，Agent 自动识别并调用 NMRProcessor 进行傅里叶变换和峰识别，产出标准的峰表报告。

### 5.3 DFT 计算全流程辅助
Agent 协助用户选择泛函与基组（通过 Skill 系统），在计算完成后调用 VASPKIT-Py 工具自动绘制能带图和 DOS 图。

---

## 六、技术支持

- **开发团队**：Cloudra Team

---

*本说明书适用于 Cloudra V1.2.0 版本*

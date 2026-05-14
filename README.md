# Cloudra ⚗️

面向化学科研的 AI Agent 协作框架。

## 🚀 快速开始

### 运行环境
确保已安装 Python 3.10+ 及相关依赖。建议使用虚拟环境。

### 使用示例
你可以直接通过命令行与 Agent 交互。系统采用**多进程架构**，支持子 Agent 的并发执行与实时监控：

```bash
# 基本用法
python3 main.py '你的化学需求'

# 示例：搜索特定领域的论文并汇总
python3 main.py '搜索钙钛矿太阳能电池论文并让 writer 整理成报告'

# 示例：继续之前的对话（传入对话 ID）
python3 main.py '继续分析这些论文' conv_20260512_150317_6ce696
```

## 📊 日志与监控

### 终端输出
系统会实时显示主进程（Coordinator）和子进程（Sub-agents）的思考过程：
- **[coordinator][reasoning]**: 导师 Agent 正在分析全局任务并拆解。
- **[writer][reasoning]**: 正在执行写入任务的子 Agent 的实时输出。
- **[thinking]**: Agent 的内部推理逻辑片段。
- **工具调用**: 实时显示正在执行的工具及其参数。

### 本地日志
日志系统采用会话隔离模式：
- **全局日志**: 位于 `logs/` 目录。
- **会话日志**: 位于 `conversations/[对话ID]/logs/`，包含该对话下所有参与 Agent 的详细记录。

## 🛠️ 核心能力

### 工具箱 (Tools)
Agent 可以调用以下工具来辅助科研工作：

| 工具 | 功能说明 |
|------|----------|
| `SubAgentLauncher` | 启动子进程 Agent 执行任务（支持同步等待 `is_wait=True` 或异步后台运行） |
| `paper_searcher` | 搜索 arXiv/ChemRxiv 论文 |
| `text_reader` | 高性能文本读取，支持行切片与大文件处理 |
| `text_writer` | 文本写入，支持 md、txt、py 等格式 |
| `bashtools` | 在独立沙箱中执行终端命令（如 git, python, g16 等） |
| `pdf2md` | 将 PDF 文献转换为 Markdown 格式以供 Agent 阅读 |
| `molecule_drawer` | 基于 RDKit 将 SMILES 转换为分子结构图（PNG/SVG），支持高亮、手性标注、原子编号等 |
| `image_reader` | 视觉感知工具，加载本地图片（PNG/JPG/WEBP）到 Agent 上下文中进行多模态分析 |

### 子 Agent 团队
系统内置了职责分明的子 Agent，由协调者根据需求动态指派：

| ID | 名称 | 职责 | 权限级别 |
|----|------|------|----------|
| a-1 | **Explorer** | 项目结构探索，负责定位文件和数据 | 只读 |
| a-2 | **Writer** | 文档秘书，负责代码编写和报告整理 | 读/写/覆盖 |
| a-3 | **Researcher** | 文献专家，负责论文检索、阅读与实验脚本运行 | 读/脚本执行 |
| a-4 | **Visionary** | 视觉信息解析专家，负责解析分子结构图、表征图谱、实验照片等 | 只读 |

---

## 📖 项目深度解析

### 1. 核心架构：多进程协作模型
Cloudra 采用了稳健的 **Manager-Worker (多进程)** 协作模式：
*   **协调者 (Coordinator)**：作为系统大脑，负责任务拆解、隔离与结果汇总。
*   **执行者 (Follower)**：在独立的子进程中运行，互不干扰，具备各自独立的上下文空间。

### 2. 推理逻辑：单循环 ReAct
系统废弃了复杂的双阶段观察模型，采用更自然的**单循环 ReAct 架构**。Agent 在同一推理流程中自主评估工具返回的结果并决定后续行动，响应速度更快且逻辑一致性更高。

### 3. 多模态上下文管理
框架支持**动态图片上下文加载**：
*   **视觉工具链**: `image_reader` 和 `molecule_drawer` 可将图像注入 Agent 的推理上下文。
*   **Token 优化**: 历史对话中的图片会自动进行信息简化（降级为文件路径引用），确保多模态交互不会消耗过多 Token。
*   **实时解析**: Visionary 子 Agent 可读取 NMR、IR、TEM/SEM 等化学表征图谱，并输出结构化文本报告。

### 4. 任务隔离与安全性
*   **Prompt 注入**: 协调者通过 `reasoning_prompt` 动态定义子 Agent 的临时身份和禁令，确保子任务严格受控。
*   **WAL 模式**: 数据库启用 WAL 模式，确保高并发下的数据一致性与读取性能。

### 5. 扩展性：Skill 系统
通过在 `skills/` 目录下添加 Markdown 文件，可以为 Agent 注入专业的化学知识。推荐参考 `subagent-prompting` 技能来学习如何更有效地给子 Agent 下达指令。

---

## 📅 版本记录

v0.2.0 (2026.05.15)
- [新增] 化学结构式绘制工具 `molecule_drawer`（基于 RDKit，支持 SVG/PNG 与高亮）。
- [新增] 视觉感知工具 `image_reader`，支持 Agent 读取并分析本地图片。
- [新增] `Visionary` 子 Agent，专用于解析分子图、表征图谱与实验影像。
- [重构] `llm_call` 与 `update_context`，支持动态向上下文加载最新图片；历史图片自动简化为路径引用以节省 Token。
- [优化] 全系统 Prompt 调优，强化多模态任务指令与视觉推理引导。

v0.1.9 (2026.05.12)
- [重构] 升级为多进程并发架构。
- [简化] 废除 observe 阶段，优化为单循环 ReAct。
- [修复] 修正 text_reader 切片逻辑与子 Agent 权限 Bug。
- [优化] 实现日志会话隔离与结果实时管道转发。

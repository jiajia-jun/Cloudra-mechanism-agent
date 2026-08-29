---
key: t58824
title: ����ֻ�ÿ�Դ����vibe code���㻯ѧ��ģС���ȫ��¼ (�����)
url: http://bbs.keinsci.com/thread-58824-1-1.html
domain: 化学信息学与脚本
source: keinsci
year: 2026
cards: 18
---

# ����ֻ�ÿ�Դ����vibe code���㻯ѧ��ģС���ȫ��¼ (�����) — 知识卡片

## 1. 开源Vibe Code构建计算化学工具的定义

Vibe code 是一种仅依靠开源资源、利用大语言模型(LLM)Agent 编程来构建工具的方法。该方法旨在尝试在不使用闭源或昂商业模型的前提下，利用开源工具开发计算化学相关的实用小工具。此过程仅使用开源模型，旨在探索低成本自动化的可行性。

---

## 2. 目标模型选择与限制策略

在应用开源模型时，建议优先选择非Top 5的模型或专注特定领域的模型，因为这些模型可能在某些特定领域比通用Top 5模型表现更好。具体的模型选择需结合算力成本和任务需求，例如通过 openrouter 选择成本更低的模型或使用 opencode 开源代码模型。使用前需要验证模型的依赖关系、支持的语言以及参数限制。

---

## 3. 小型开源模型的Context Window管理策略

小型开源模型的 Context Window 大约为 200K token，因此 orchestrator - subagent 架构在此场景下非常有效。建议将每个 session 的 context window 通过 orchestrator 控制，限制在 50% (约 100K tokens) 左右，以便将剩余空间留给 sub-agent 使用。这种分配策略有助于防止上下文溢出并保持多轮对话的连贯性。

---

## 4. 调试阶段的资源消耗与优化

Debug 过程可能会消耗大量 context，因此建议创建专门的 debug session，引入 debug subagent 和 debug workflow 来处理错误。针对模型可能产生的假引用问题，必须人工重复要求验证，或者通过人工检查确保提供的 reference link 是真实存在的。

---

## 5. v1 核心逻辑开发里程碑规划

v1 版本侧重于核心逻辑的构建，总耗时约 3 个月，成本为 60 USD。该阶段消耗的 token 总量为 Input 36.3M / Output 1.7M / Cache Read 140.0M / Cache Write 1.3M。

---

## 6. v2 图形界面开发里程碑规划

v2 版本致力于图形界面工作，与 v1 累计成本达 160 USD。该阶段消耗的 token 总量累计为 Input 103.8M / Output 3.3M / Cache Read 284.8M / Cache Write 2.1M。

---

## 7. 开源Agent工作流的循环步骤

项目执行采用开源的 markdown agent 和 slash command 模式，工作流包含从项目定义到里程碑完成的多个循环步骤。标准流程包括：new project (milestone) definition、收集需求、规划 milestone 和项目、foundation research、创建 milestone 和 phase 的 roadmap、详细计划并实施每个 phase、验证并 tag release、扩展下一个 milestone。

---

## 8. 单个Phase的执行流程

每个具体的 Phase 执行遵循严格的步骤顺序：首先进行 discuss 和 Research，随后制定 Plan 并进行 plan checking（如需则修订），接着 execute 执行计划。之后进入 verify -> debug -> verify 的循环直至结果正确，最后进行 UAT（用户验收测试）。

---

## 9. 项目初始Prompt的构建要素

项目启动时的 Prompt 文件需包含当前 conda 环境中通过 @environment.yml 安装的 XXX 库列表。Prompt 需指明推导 XXXX 框架的要求，明确最终成果需包含 A、B、C、D 等组成部分，并规定文档 X 的风格、语气 Y 及目标受众 Z。

---

## 10. v1 核心逻辑开发的功能阶段分解

v1 核心逻辑开发细分为以下七个主要阶段：1. Input validation；2. Condition mapping；3. Structure generation；4. Scoring and Ranking；5. Output；6. Documentation；7. Audit。

---

## 11. v1 阶段常见Bug与修复

v1 阶段常需要进行 Bugfix phase，常见问题包括遗漏重要数据点以及代码扫描发现的嵌套 for-loop 影响速度的问题。该阶段的大部分时间和 token 消耗主要集中在结构生成数据的构建上。

---

## 12. v1 交付物验证标准

v1 完成后的验证工作包括：Review citation 并验证文档中的链接是否有效；扫描代码库以查找关键 bug；扫描代码以确认 CLI 命令、提示信息以及图像协议等相关功能是否完整且符合设计规范。

---

## 13. v2 图形界面需求规范

v2 版本要求基于 v1 发布后，创建一个轻量级、独立、跨平台的 GUI 可执行程序（支持 Windows 和 Linux 64 位）。GUI 需具备全功能一体化界面，包括特定功能 Feature A、选项输入框、带引用的信息窗口、生成 3D 结构的按钮、进度条、节省资源的单分子 3D 查看器（棍状/球棍模型/氢键虚线）以及保存绘图/结构/导出数据的选项。

---

## 14. v2 图形界面开发注意事项

v2 开发中的 Notes 要求：限制生成分子的数量以控制负载；为每个选项提供极简解释（如 `i` 或 `?` 标识），并辅以基于 Markdown 手册生成的 PDF 截图手册。此外，必须检查所用库的许可证，确认当前选定的许可证是否允许作为独立可执行文件进行分发。

---

## 15. v2 图形界面开发的功能阶段分解

v2 图形界面开发细分为以下六个主要阶段：8. GUI infrastructure and core input；9. Interactive [feature XXX]；10. 3D molecular viewer；11. Save, export, and in-app information；12. v2 Documentation update；13. Packaging and distribution。

---

## 16. v2 阶段常见Bug与修复

v2 阶段的 3D 显示功能较为复杂，通常需要大量的 debug 时间。在 Phase 9 调试 GUI 时，可能会顺带修复 v1 版本遗留的一个绘图小 bug。

---

## 17. 模型交互中的常见问题与拒绝处理

在与 LLM 交互时，频繁使用 reject/approve/PUA 指令可能导致模型拒绝响应或产生防御性输出，这在大小模型中都存在风险。模型可能会在无关的 motivation 等非关键内容上消耗大量 token，或在面对 Deny、rm 等指令时产生不必要的冗余对话。

---

## 18. 调试反馈的有效性

Debug 阶段的效果取决于反馈的有效性。如果仅仅提出笼统的问题（如 "very disappointing"），无法帮助模型定位和解决问题，调试效果将大打折扣。

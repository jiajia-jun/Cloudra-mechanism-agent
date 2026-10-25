# 前端主题与聊天布局迁移

> **For agentic workers:** Use superpowers:subagent-driven-development; work in the current branch as explicitly requested by the user.

**Goal:** 在当前 master 复刻 `166131e4` 的布局、glass/emerald 主题和界面操作。

**Architecture:** 迁移主题样式和独立组件，在当前 App 与设置页中接入；保留新版事件流、消息回执、审批、Codex 登录、搜索和工具文档配置。后端协议不变，不引入依赖。

**Tech Stack:** React、TypeScript、Vite、Playwright。

**Spec:** 本次对话已确认的 `codex/ui-themes-chat-layout` 版本；用户要求在当前分支复刻。

## 任务

- [x] 迁移主题、侧栏、项目/文件夹/模型/定时任务组件。
- [x] 迁移设置外观页，同时保留现有配置能力。
- [x] 在当前 App 中接入布局和首次发送自动创建聊天；共用现有项目创建与消息发送逻辑。
- [x] 迁移交互用例，验证主题持久化、首次发送、模型选择和现有审批/消息/取消入口。
- [x] 构建、相关前端单测及浏览器检查；独立审查后提交推送 master。

## 验证重点

新聊天只创建一次项目并发送一次请求；创建失败保留输入；异步旧结果不覆盖新选择。
主题刷新后保持；模型选择保留现有推理强度；新版设置及 Benchmark 入口仍能访问。
只使用模拟 API 测试，不启动计算或改动研究数据。

## 验证记录

生产构建、`compileall`、Ruff、四个相关前端单测脚本及 72 项模拟浏览器回归通过。
另外两个受控制台入口定位影响的科学展示用例通过，科学断言保持不变。
独立源码审查未发现阻断问题；两套主题完成桌面与 390px 窄屏目视检查。
迁移同时修复默认推理强度无法清空、模型按钮回显、保存后 Escape 无法关闭菜单、文件夹菜单遮挡，以及提交时草稿输入与窄屏侧栏挤压。

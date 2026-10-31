# 配置指南

[English](CONFIGURATION.md) · [返回文档中心](README.md)

先按[首页](../README_CN.md)完成安装。在全局设置中填写主 Agent 与协作 Agent 的提供商、模型名称和凭据；量子化学软件与计算节点按具体研究任务单独配置。

## 服务与远程访问

```bash
cloudra                      # 构建前端并启动服务，自动打开浏览器
cloudra web --skip-build     # 复用已构建的前端
cloudra web --host 0.0.0.0   # 允许其他机器访问
```

默认监听 `127.0.0.1:8000`。远程访问时使用终端显示的 `#token=` 链接；任何能连接监听地址的机器都可以用此令牌访问。访问控制依赖 bearer token，`Authorization: Bearer …` 与 `?token=` 等价，适用于所有 HTTP 方法，不检查 Host。非本机监听时不要设置 `CLOUDRA_API_TOKEN=off`。

## 对话命令

在主聊天框中键入 `/`，可以查看可用命令，支持键盘选择与 Tab 补全：

- `/schedule [on|off]`：切换自主调度模式。开启后，没有有效自唤醒提醒的停止请求会被拦截，便于在长计算期间挂起并恢复研究。
- `/goal <任务目标描述>`：为当前会话锚定核心研究目标。该目标经过多轮上下文压缩依然常驻。
- `/yolo [on|off]`：切换自动审批（YOLO模式），由自动审批策略评估需要授权的操作；权限和科学证据要求仍然适用。
- `/compact`：手动触发上下文结构化压缩，生成带文件交接指针的摘要并归档历史。
- `/help`：快速呼出指令指南。

## 联网搜索

默认 `search` 使用 DeepSeek Search，`browser` 使用 DeepSeek Fetch 读取页面正文；截图与显式等待仍走浏览器。Search 与 Fetch 共用一把密钥，独立于语言模型。在全局设置中配置，或运行：

```bash
cloudra config set search_provider deepseek
cloudra config set deepseek_api_key YOUR_DEEPSEEK_API_KEY
```

也支持 `CLOUDRA_SEARCH_PROVIDER` 和 `CLOUDRA_DEEPSEEK_API_KEY` 环境变量。可选提供商为 `deepseek`（默认）、`auto`、`tavily`、`brave`、`bing` 和 `duckduckgo`。指定提供商时，缺少凭据或请求失败会直接报错；`auto` 依次尝试 DeepSeek、Tavily、Brave、Bing 和 DuckDuckGo。Tavily 与 Brave 分别使用 `TAVILY_API_KEY`、`BRAVE_SEARCH_API_KEY`；非 DeepSeek 提供商继续通过浏览器读取页面正文。

DeepSeek 模型原生搜索需显式开启；`native_search=auto` 仍使用独立搜索工具。开启方式：

```bash
cloudra config set coordinator.native_search deepseek
```

其他模型提供商保持原有原生搜索行为；在相应模型配置中设 `native_search=off` 可改用独立搜索工具。

## ChatGPT / Codex 登录

在全局设置中选择 **OpenAI Codex（ChatGPT 账号）**，点击登录按钮，在授权页面输入设备码，完成后保存主 Agent 或协作 Agent 的模型配置。二者共用 Cloudra 保存的账号登录。

```bash
cloudra auth codex login
cloudra config set coordinator.provider openai-codex
cloudra config set coordinator.model gpt-6-sol
cloudra config set follower.provider openai-codex
cloudra config set follower.model gpt-6-sol
cloudra auth codex status
cloudra auth codex logout
```

提供商别名也接受 `codex` 和 `openai_codex`。可用模型取决于账号权限；账号或工作区安全设置可能需要开启设备授权，见 [OpenAI 身份验证说明](https://developers.openai.com/codex/auth/)。

## 工具运行环境

默认 JavaScript 协议需要 Node.js ≥ 22 及首页安装步骤中的宿主依赖。可选的 `traditional` 协议不使用 JS 宿主。调用协议和工具文档加载机制见[开发者说明](TOOL_PROTOCOLS.md)。

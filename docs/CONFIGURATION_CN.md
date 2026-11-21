# 配置指南

[English](CONFIGURATION.md) · [返回文档中心](README.md)

装好 Cloudra 之后，大部分常用配置都能直接在网页里的 **全局设置（Global Settings）** 点完。这里补充命令行启动、远程访问、斜杠命令、联网搜索、Codex 登录和外部 MCP 服务的配置方法。

## 启动服务与远程访问

```bash
cloudra                      # 编译前端、启动服务并自动打开浏览器
cloudra web --skip-build     # 跳过前端编译，直接启动
cloudra web --host 0.0.0.0   # 监听所有网卡，允许局域网或远程访问
```

服务默认只监听本机 `127.0.0.1:8000`。

如果你把服务开在远程服务器上，启动后终端会打印一条带 `#token=` 的完整链接，直接用这条链接打开就能登录。接口鉴权只认这个令牌（请求头 `Authorization: Bearer …` 和 URL 参数 `?token=` 都可以，不限 HTTP 方法，也不挑 Host）。只要监听了非本机地址，就千万别把 `CLOUDRA_API_TOKEN` 设成 `off`。

## 聊天框里的斜杠命令

在输入框里打 `/` 就能弹出命令菜单，支持方向键和 Tab 补全：

- `/schedule [on|off]`：开关“自主值守”模式。打开后，如果后台还有长计算没完、Agent 却没设唤醒提醒就想停下来，系统会把它拦住，方便它在跑计算时安心休眠、算完自动醒来接着干。
- `/goal <目标>`：把当前的核心研究目标钉死在上下文里，就算后面聊得很长、触发了上下文压缩也不会忘。
- `/yolo [on|off]`：开关自动审批模式。开启后系统会用自动策略替你审常规操作，但基础权限红线和科学证据门槛不会放水。
- `/compact`：手动压缩一遍历史对话，把旧内容归档成带文件路径交接信息的摘要，腾出上下文空间。
- `/help`：列出所有可用命令。

## 联网搜索

默认情况下，搜索工具 `search` 走 DeepSeek Search，网页正文读取走 DeepSeek Fetch（需要截图或等待页面渲染时还是用真实浏览器）。这两个共用一把密钥，和你聊天用的大模型密钥互不相干。除了在全局设置里填，也可以用命令行配：

```bash
cloudra config set search_provider deepseek
cloudra config set deepseek_api_key YOUR_DEEPSEEK_API_KEY
```

也支持环境变量 `CLOUDRA_SEARCH_PROVIDER` 和 `CLOUDRA_DEEPSEEK_API_KEY`。

可选的搜索后端有 `deepseek`（默认）、`auto`、`tavily`、`brave`、`bing` 和 `duckduckgo`。指定某个具体后端时，缺密钥或请求失败会直接报错；选 `auto` 会按 DeepSeek → Tavily → Brave → Bing → DuckDuckGo 的顺序往下试。Tavily 和 Brave 的密钥分别读 `TAVILY_API_KEY` 和 `BRAVE_SEARCH_API_KEY`。非 DeepSeek 后端统一用浏览器抓网页正文。

如果你想用 DeepSeek 模型自带的原生联网搜索，需要手动打开（默认 `native_search=auto` 仍走独立的 `search` 工具）：

```bash
cloudra config set coordinator.native_search deepseek
```

其他厂商的模型默认保留各自原本的原生搜索行为；想强制关掉原生搜索、统一走独立搜索工具，把对应槽位的 `native_search` 设成 `off` 就行。

## ChatGPT / Codex 账号登录

不想配 API Key，也可以直接用 ChatGPT 账号。在全局设置里把供应商选成 **OpenAI Codex（ChatGPT 账号）**，点登录按钮拿到设备码去网页授权，完成后保存主 Agent 或协作 Agent 配置就行，两个槽位共用同一个登录态。

命令行也能直接配：

```bash
cloudra auth codex login
cloudra config set coordinator.provider openai-codex
cloudra config set coordinator.model gpt-6-sol
cloudra config set follower.provider openai-codex
cloudra config set follower.model gpt-6-sol
cloudra auth codex status
cloudra auth codex logout
```

供应商名字也认 `codex` 和 `openai_codex`。具体能用哪些模型取决于你的账号权限；如果账号或团队工作区默认关了设备码登录，需要先按 [OpenAI 认证说明](https://developers.openai.com/codex/auth/) 打开。

## 工具运行环境

Cloudra 默认用 JavaScript 协议让 Agent 编排工具调用，这需要本机有 **Node.js ≥ 22** 以及 `install.sh` 装好的宿主依赖。如果不想装 Node.js，可以在 Agent 设置里切换成 `traditional` 协议（每次调一个工具，不依赖 JS 宿主）。底层机制见[工具协议说明](TOOL_PROTOCOLS.md)。

## 接入外部 MCP 工具

如果你想把实验室自己的脚本或外部工具接进 Cloudra，先装好 MCP 依赖：`pip install 'cloudra[mcp]'`（装了 `cloudra[all]` 的已经自带）。

然后运行 `cloudra config get config_file` 找到配置文件路径，往里面的 YAML 加一段 `mcp_servers` 并重启服务：

```yaml
mcp_servers:
  local_lab:
    command: python
    args: ["/absolute/path/lab_server.py"]
    env:
      LAB_API_KEY: "your-key"
  remote_lab:
    url: https://lab.example.org/mcp
    headers:
      Authorization: "Bearer your-token"
```

本地进程（stdio）必填 `command`，可选 `args`、`env`、`cwd`；远程服务（Streamable HTTP）必填 `url`，可选 `headers`。

接入之后，外部工具会以 `mcp__服务名__工具名` 的形式自动出现在新建会话的工具目录里（名字太长或含特殊字符时程序会自动规整）。你照常在聊天框里提需求就行，不用记特殊语法。旧会话不会热加载新工具，改完配置重启后开新会话或新子 Agent 即可生效。

权限方面，每个 MCP 服务都能配一个可选的 `permissions` 字段，复用 Cloudra 现有的 `read` / `write` / `manage` / `script` / `destructive` 开关（默认需要 `read` 和 `script`）。高风险服务加上 `destructive: true` 就会走人工审批。配置文件里的密钥在界面和 CLI 查询时都会自动打码隐藏。注意外部工具返回“执行成功”只说明程序跑通了，科学结论该怎么验收还是按 Cloudra 原本的证据标准来。

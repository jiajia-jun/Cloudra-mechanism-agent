# Configuration

[中文](CONFIGURATION_CN.md) · [Back to documentation](README_EN.md)

Start with the installation steps in the [README](../README.md). Configure the coordinator and follower model providers, model names and credentials in Global Settings. Quantum-chemistry engines and compute nodes must be configured separately for the intended study.

## Server and remote access

Cloudra features a unified, single-port web interface (FastAPI control plane + React/Vite SPA):

```bash
cloudra                      # Builds the frontend and starts the server, opening your browser
cloudra web --skip-build     # Fast restart using pre-built assets
cloudra web --host 0.0.0.0   # Bind a custom address/port (LAN / remote UI)
```

> Access control is the bearer token only: `Authorization: Bearer …` and `?token=`
> are equivalent, any HTTP method, no Host check. Open the printed `#token=` URL
> from any machine that can reach the bind address. Default bind is
> `127.0.0.1:8000`. Do not use `CLOUDRA_API_TOKEN=off` on a non-loopback bind.

## Chat commands

Type `/` in the chat composer to see available commands:

- `/schedule [on|off]`: Toggle autonomous schedule mode. When active, stopping without an active self-wake reminder is intercepted, protecting long unattended computational runs.
- `/goal <description>`: Pin the primary research objective for the active agent, preserved even across aggressive context compactions.
- `/yolo [on|off]`: Toggle automated policy review (YOLO mode). Permission and scientific evidence requirements still apply.
- `/compact`: Trigger structured context compaction, archiving past trajectory turns and emitting handover summaries.
- `/help`: Display slash command usage and syntax.

## Web search

The existing `search` tool uses DeepSeek Search by default. The existing `browser`
tool uses DeepSeek Fetch for page text and returns Markdown; screenshots and
explicit page waits still use the browser. Search and Fetch share one API key,
independent of the selected language model. Configure both in Global Settings or:

```bash
cloudra config set search_provider deepseek
cloudra config set deepseek_api_key YOUR_DEEPSEEK_API_KEY
```

Environment variables `CLOUDRA_SEARCH_PROVIDER` and `CLOUDRA_DEEPSEEK_API_KEY` are
also supported. Provider choices are `deepseek` (default), `auto`, `tavily`,
`brave`, `bing`, and `duckduckgo`. A selected provider reports missing credentials
or request failures directly. `auto` tries DeepSeek, Tavily, Brave, Bing, then
DuckDuckGo; Tavily and Brave use `TAVILY_API_KEY` and `BRAVE_SEARCH_API_KEY`.
Non-DeepSeek providers keep the existing browser path for page text.

DeepSeek model-native search is opt-in; `native_search=auto` keeps the independent
search tool for DeepSeek. To explicitly enable its model-native search:

```bash
cloudra config set coordinator.native_search deepseek
```

Other model providers retain their existing native-search behavior. Use
`native_search=off` on a model slot to use the independent search tool instead.

## ChatGPT / Codex login

Select **OpenAI Codex (ChatGPT account)** in Global Settings, click the ChatGPT / Codex login button, open the authorization page and enter the displayed device code. After authorization, save the coordinator and/or follower model configuration. Both slots share the Cloudra account login.

The same flow is available from the CLI:

```bash
cloudra auth codex login
cloudra config set coordinator.provider openai-codex
cloudra config set coordinator.model gpt-6-sol
cloudra config set follower.provider openai-codex
cloudra config set follower.model gpt-6-sol
cloudra auth codex status
# Sign out of the Cloudra account session:
cloudra auth codex logout
```

The provider accepts the aliases `codex` and `openai_codex`. Model access depends on your ChatGPT account. Device authorization may need to be enabled in your ChatGPT account or workspace security settings; see [OpenAI authentication guidance](https://developers.openai.com/codex/auth/).


## Tool runtime

The default JavaScript protocol requires Node.js ≥ 22 and the host dependencies installed in the README. The optional `traditional` protocol does not use the JS host. Protocol behavior and documentation loading are described in [Tool protocols](TOOL_PROTOCOLS.md).

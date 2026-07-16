# ycyc 中转站使用反馈（Issue 草稿）

> 这份 issue 用于反馈在使用 ycyc 中转站（`https://ycyc.star.dpdns.org/v1`）调用 `gpt-5.5` 时遇到的两个问题。语气已尽量委婉，重点把现象和我们的处理方式写清楚，方便对方定位。

---

## 环境信息

- **中转站**：`https://ycyc.star.dpdns.org/v1`
- **模型**：`gpt-5.5`
- **客户端**：OpenAI Python SDK (`openai>=1.0`)
- **调用方式**：`chat.completions.create(..., tools=[...], stream=True/False)`
- **用途**：我们正在开发一个多 Agent 科研助手框架 [Cloudra](https://github.com/YYY2333/CLOUDRA)，对 function calling 和流式输出依赖较重。

---

## 问题一：默认请求头会被拦截

### 现象

使用 OpenAI 官方 SDK 的默认请求头直接请求时，会返回：

```text
Your request was blocked.
```

### 我们的处理

我们在客户端做了三级 fallback，最终才能正常请求：

1. OpenAI 默认请求头 → 被拦截
2. OpenAI SDK + 自定义 `User-Agent: curl/7.68.0` → 部分请求可以通过
3. 降级到 `requests` 库 + `User-Agent: curl/7.68.0` → 可以通过

```python
# 第 2/3 级能走通的关键是把 User-Agent 改成 curl
headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json",
    "User-Agent": "curl/7.68.0",
    "Accept": "application/json",
}
```

### 建议

如果方便的话，能否让 OpenAI 官方 SDK 的默认请求头也能直接通过？这样下游项目就不需要额外维护 fallback 逻辑了。

---

## 问题二：Function Calling 返回的 `function.name` 为空

### 现象

在 `tools` 参数正确传入、且模型明显知道该调用哪个工具的情况下，返回的 `tool_calls[].function.name` 是空字符串，但 `arguments` 里的参数是正确的。

一个典型的返回片段如下（来自 `chat.completions.create` 的流式 chunk）：

```json
{
  "tool_calls": [
    {
      "index": 0,
      "id": "call_xxx",
      "type": "function",
      "function": {
        "name": "",
        "arguments": "{\"skill_name\":\"subagent-prompting\"}"
      }
    }
  ]
}
```

同样，`stop` 工具也会出现：

```json
{
  "function": {
    "name": "",
    "arguments": "{\"reason\":\"...\",\"final_answer\":\"...\"}"
  }
}
```

### 影响

按照 OpenAI 的 function calling 规范，`function.name` 是必填字段。如果它为空，客户端无法直接把调用路由到对应工具，会导致：

- 工具调用失败
- Agent 反复重试同一个空名调用
- 进入死循环

### 我们的处理

为了兼容这种情况，我们在框架里加了兜底推断：当 `function.name` 为空时，根据 `arguments` 里的参数集合，反推最可能匹配的工具名。

推断顺序：

1. 精确匹配工具全部参数字段集合
2. 精确匹配工具的 `required` 字段集合
3. 模糊匹配：找 `required` 字段是 `arguments` 子集且重合度最高的工具

例如：

- `{"skill_name": "..."}` → 推断为 `getskill`
- `{"reason": "...", "final_answer": "..."}` → 推断为 `stop`

这个方法能跑通，但本质上是在补全一个本应由服务端/模型返回的字段。对每个新增工具，虽然映射是自动从 schema 生成的，但总归增加了客户端的维护负担。

### 建议

如果方便排查的话，能否确认一下 `gpt-5.5` 在 function calling 时 `function.name` 被置空的原因？理想情况下，返回的 tool_call 应该携带完整且正确的 `name`，这样下游框架可以直接按标准 OpenAI 格式处理。

---

## 总结

| 问题 | 严重程度 | 当前 workaround |
|------|----------|-----------------|
| 默认请求头被拦截 | 中等 | 自定义 User-Agent + requests fallback |
| `function.name` 为空 | 较高 | 根据 arguments 反推工具名 |

如果 ycyc 侧能修复这两点，下游项目就可以去掉这些 workaround，对两边都好维护。感谢！

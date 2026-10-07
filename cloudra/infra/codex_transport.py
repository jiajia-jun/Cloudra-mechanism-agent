"""OAuth-only Codex Responses transport, adapted to Cloudra's chat contract."""

import asyncio
import json
from typing import Any

import httpx
import openai

from cloudra import __version__
from cloudra.infra.codex_auth import CODEX_BASE_URL, resolve_codex_credentials


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"Codex {label} must be a string")
    return value


def _identity(value: Any, label: str) -> str:
    value = _text(value, label)
    if not value or value != value.strip():
        raise ValueError(f"Codex {label} must be non-empty without surrounding whitespace")
    return value


def _content(value: Any, role: str) -> list[dict]:
    text_type = "output_text" if role == "assistant" else "input_text"
    if value is None:
        return []
    if isinstance(value, str):
        return [{"type": text_type, "text": value}]
    if not isinstance(value, list):
        raise ValueError("Codex message content must be text or a list of parts")
    parts = []
    for part in value:
        if not isinstance(part, dict):
            raise ValueError("Codex content part must be an object")
        kind = part.get("type")
        if kind in ("text", "input_text", "output_text"):
            parts.append({"type": text_type, "text": _text(part.get("text"), "content text")})
        elif kind in ("image_url", "input_image") and role == "assistant":
            parts.append({"type": "output_text", "text": "[Image in previous assistant message]"})
        elif kind == "image_url" and role != "assistant":
            image = part.get("image_url")
            if not isinstance(image, dict):
                raise ValueError("Codex image_url must be an object")
            entry = {"type": "input_image", "image_url": _text(image.get("url"), "image URL")}
            if image.get("detail") is not None:
                entry["detail"] = image["detail"]
            parts.append(entry)
        elif kind == "input_image" and role != "assistant":
            parts.append({"type": "input_image", "image_url": _text(part.get("image_url"), "image URL")})
        else:
            raise ValueError(f"Unsupported Codex content part: {kind!r}")
    return parts


def _tool_output(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    parts = _content(content, "user")
    return "\n".join(part.get("text", "[Image attached to this tool result]") for part in parts)


def _build_payload(kwargs: dict) -> dict:
    model = _text(kwargs.get("model"), "model").strip()
    if not model:
        raise ValueError("Codex model must be non-empty")
    inputs, instructions = [], []
    call_ids, pending_calls = set(), set()
    leading_system = True
    messages = kwargs.get("messages") or []
    if not isinstance(messages, list):
        raise ValueError("Codex messages must be a list")
    for message in messages:
        if not isinstance(message, dict):
            raise ValueError("Codex message must be an object")
        role = message.get("role")
        content = message.get("content")
        if role == "system" and leading_system:
            instructions.extend(part["text"] for part in _content(content, "developer"))
            continue
        leading_system = False
        if role in ("user", "assistant", "developer", "system"):
            wire_role = "developer" if role == "system" else role
            parts = _content(content, wire_role)
            if parts:
                inputs.append({"type": "message", "role": wire_role, "content": parts})
            # Plain reasoning_content is a display summary, not replayable encrypted reasoning.
            for call in message.get("tool_calls") or []:
                if not isinstance(call, dict) or call.get("type") != "function":
                    raise ValueError("Codex tool call must be a function call")
                function = call.get("function")
                if not isinstance(function, dict):
                    raise ValueError("Codex function call must be an object")
                call_id = _identity(call.get("id"), "function call ID")
                if call_id in call_ids:
                    raise ValueError("Duplicate Codex function call ID")
                call_ids.add(call_id)
                pending_calls.add(call_id)
                inputs.append({
                    "type": "function_call",
                    "call_id": call_id,
                    "name": _identity(function.get("name"), "function name"),
                    "arguments": _text(function.get("arguments"), "function arguments"),
                })
        elif role == "tool":
            call_id = _identity(message.get("tool_call_id"), "tool output call ID")
            if call_id not in pending_calls:
                raise ValueError("Codex tool output does not match a pending function call")
            pending_calls.remove(call_id)
            inputs.append({
                "type": "function_call_output",
                "call_id": call_id,
                "output": _tool_output(content),
            })
        else:
            raise ValueError(f"Unsupported Codex message role: {role!r}")
    payload: dict[str, Any] = {
        "model": model,
        "instructions": "\n\n".join(instructions),
        "input": inputs,
        "store": False,
        "stream": True,
    }
    tools = []
    for tool in kwargs.get("tools") or []:
        if not isinstance(tool, dict) or tool.get("type") != "function":
            raise ValueError("Codex supports function tools in Cloudra")
        function = tool.get("function")
        if not isinstance(function, dict):
            raise ValueError("Codex tool function must be an object")
        entry = {"type": "function", "name": _identity(function.get("name"), "tool name")}
        for key in ("description", "parameters", "strict"):
            if key in function:
                if key == "strict" and not isinstance(function[key], bool):
                    raise ValueError("Codex tool strict flag must be a boolean")
                entry[key] = function[key]
        tools.append(entry)
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    if "tool_choice" in kwargs:
        choice = kwargs["tool_choice"]
        if isinstance(choice, dict):
            function = choice.get("function") or {}
            if choice.get("type") != "function" or not isinstance(function, dict):
                raise ValueError("Invalid Codex tool choice")
            choice = {"type": "function", "name": _text(function.get("name"), "chosen tool name")}
        payload["tool_choice"] = choice
    if "parallel_tool_calls" in kwargs:
        if not isinstance(kwargs["parallel_tool_calls"], bool):
            raise ValueError("Codex parallel_tool_calls flag must be a boolean")
        payload["parallel_tool_calls"] = kwargs["parallel_tool_calls"]
    if kwargs.get("reasoning_effort"):
        payload["reasoning"] = {"effort": kwargs["reasoning_effort"], "summary": "auto"}
    # Chat sampling/token limits and arbitrary extra_body/header overrides are unsupported here.
    return payload


def _wrap(data: dict):
    from cloudra.infra.llm_client import ResponseDictWrapper

    return ResponseDictWrapper(data)


class _ResponseState:
    def __init__(self):
        self.id = None
        self.texts: dict[int, str] = {}
        self.phases: dict[int, str | None] = {}
        self.reasoning = ""
        self.tools: dict[int, dict] = {}
        self.usage = None
        self.finish = None

    def _chunk(self, *, content=None, reasoning=None, tools=None, finish=None):
        return _wrap({
            "id": self.id,
            "object": "chat.completion.chunk",
            "choices": [{"index": 0, "delta": {
                "content": content, "reasoning_content": reasoning, "tool_calls": tools,
            }, "finish_reason": finish}],
            "usage": self.usage if finish else None,
        })

    @staticmethod
    def _index(event: dict) -> int:
        index = event.get("output_index", 0)
        if not isinstance(index, int) or isinstance(index, bool) or index < 0:
            raise RuntimeError("Malformed Codex output index")
        return index

    def _tool(self, index: int, item: dict) -> list:
        call_id, name = item.get("call_id"), item.get("name")
        if not isinstance(call_id, str) or not call_id or not isinstance(name, str) or not name:
            raise RuntimeError("Codex function call is missing its identity")
        emitted = []
        state = self.tools.get(index)
        if state is None:
            state = {"index": len(self.tools), "id": call_id, "name": name, "arguments": ""}
            self.tools[index] = state
            emitted.append(self._chunk(tools=[{
                "index": state["index"], "id": call_id, "type": "function",
                "function": {"name": name, "arguments": ""},
            }]))
        elif state["id"] != call_id or state["name"] != name:
            raise RuntimeError("Codex function call identity changed")
        arguments = item.get("arguments")
        if arguments is not None:
            emitted.extend(self._arguments(index, arguments, complete=True))
        return emitted

    def _arguments(self, index: int, arguments: Any, *, complete: bool) -> list:
        if index not in self.tools or not isinstance(arguments, str):
            raise RuntimeError("Malformed Codex function arguments")
        state = self.tools[index]
        if complete:
            if not arguments.startswith(state["arguments"]):
                raise RuntimeError("Codex function argument deltas disagree with completed call")
            delta = arguments[len(state["arguments"]):]
        else:
            delta = arguments
        state["arguments"] += delta
        if not delta:
            return []
        return [self._chunk(tools=[{"index": state["index"], "function": {"arguments": delta}}])]

    def _item(self, index: int, item: Any) -> list:
        if not isinstance(item, dict):
            raise RuntimeError("Malformed Codex output item")
        kind = item.get("type")
        if kind == "function_call":
            return self._tool(index, item)
        if kind == "message":
            phase = item.get("phase")
            if phase not in (None, "commentary", "final_answer"):
                raise RuntimeError("Malformed Codex assistant phase")
            self.phases[index] = phase
            if phase == "commentary":
                return []
            content = item.get("content") or []
            if not isinstance(content, list):
                raise RuntimeError("Malformed Codex output message")
            text = ""
            for part in content:
                if not isinstance(part, dict):
                    raise RuntimeError("Malformed Codex output content")
                if part.get("type") == "output_text":
                    if not isinstance(part.get("text"), str):
                        raise RuntimeError("Malformed Codex output text")
                    text += part["text"]
                elif part.get("type") == "refusal":
                    if not isinstance(part.get("refusal"), str):
                        raise RuntimeError("Malformed Codex refusal text")
                    text += part["refusal"]
            previous = self.texts.get(index, "")
            if not text.startswith(previous):
                raise RuntimeError("Codex text deltas disagree with completed message")
            delta = text[len(previous):]
            self.texts[index] = text
            return [self._chunk(content=delta)] if delta else []
        if kind == "reasoning":
            summary = item.get("summary") or []
            if not isinstance(summary, list):
                raise RuntimeError("Malformed Codex reasoning summary")
            text = "".join(part.get("text", "") for part in summary if isinstance(part, dict) and part.get("type") == "summary_text")
            if text and not self.reasoning:
                self.reasoning = text
                return [self._chunk(reasoning=text)]
        return []

    def process(self, event: dict) -> list:
        kind = event.get("type")
        if not isinstance(kind, str) or not kind:
            raise RuntimeError("Codex event is missing its type")
        if kind in ("error", "response.failed"):
            raise RuntimeError("Codex Responses request failed")
        index = self._index(event)
        if kind in ("response.output_text.delta", "response.refusal.delta"):
            delta = event.get("delta")
            if not isinstance(delta, str):
                raise RuntimeError("Malformed Codex text delta")
            if self.phases.get(index) == "commentary":
                return []
            self.texts[index] = self.texts.get(index, "") + delta
            return [self._chunk(content=delta)]
        if kind in ("response.reasoning_summary_text.delta", "response.reasoning_text.delta"):
            delta = event.get("delta")
            if not isinstance(delta, str):
                raise RuntimeError("Malformed Codex reasoning delta")
            self.reasoning += delta
            return [self._chunk(reasoning=delta)]
        if kind == "response.output_item.added":
            item = event.get("item")
            if not isinstance(item, dict):
                raise RuntimeError("Malformed Codex added output item")
            if item.get("type") == "function_call":
                return self._tool(index, item)
            if item.get("type") == "message":
                phase = item.get("phase")
                if phase not in (None, "commentary", "final_answer"):
                    raise RuntimeError("Malformed Codex assistant phase")
                self.phases[index] = phase
        elif kind == "response.function_call_arguments.delta":
            return self._arguments(index, event.get("delta"), complete=False)
        elif kind == "response.function_call_arguments.done":
            return self._arguments(index, event.get("arguments"), complete=True)
        elif kind == "response.output_item.done":
            return self._item(index, event.get("item"))
        elif kind in ("response.completed", "response.incomplete"):
            response = event.get("response")
            if not isinstance(response, dict):
                raise RuntimeError("Malformed Codex terminal response")
            if response.get("status") == "failed" or response.get("error"):
                raise RuntimeError("Codex Responses request failed")
            expected_status = "incomplete" if kind == "response.incomplete" else "completed"
            if response.get("status") != expected_status:
                raise RuntimeError("Codex terminal event disagrees with response status")
            self.id = response.get("id")
            emitted = []
            output = response.get("output")
            if output is not None:
                if not isinstance(output, list):
                    raise RuntimeError("Malformed Codex terminal output")
                for idx, item in enumerate(output):
                    emitted.extend(self._item(idx, item))
            usage = response.get("usage")
            if usage is not None:
                if not isinstance(usage, dict):
                    raise RuntimeError("Malformed Codex token usage")
                from cloudra.infra.llm_client import _translate_responses_usage

                self.usage = _translate_responses_usage(response)
            if expected_status == "completed" and not self.tools and not any(self.texts.values()):
                raise RuntimeError("Codex completed without a final answer or function call")
            self.finish = "length" if expected_status == "incomplete" else "tool_calls" if self.tools else "stop"
            emitted.append(self._chunk(finish=self.finish))
            return emitted
        return []

    def completion(self):
        return _wrap({
            "id": self.id,
            "object": "chat.completion",
            "choices": [{"index": 0, "message": {
                "role": "assistant",
                "content": "".join(self.texts[index] for index in sorted(self.texts)) or None,
                "reasoning_content": self.reasoning or None,
                "tool_calls": [{"id": tool["id"], "type": "function", "function": {
                    "name": tool["name"], "arguments": tool["arguments"],
                }} for tool in self.tools.values()] or None,
            }, "finish_reason": self.finish}],
            "usage": self.usage,
        })


class CodexTransport:
    """Own the asynchronous HTTP connection pool and active OAuth streams."""

    def __init__(self, owner):
        self.owner = owner
        self.client = httpx.AsyncClient(timeout=owner.timeout, follow_redirects=False)
        self.responses: set[httpx.Response] = set()

    async def aclose(self):
        for response in list(self.responses):
            await response.aclose()
        self.responses.clear()
        await self.client.aclose()

    async def _send(self, payload: dict, credentials: dict) -> httpx.Response:
        owner = self.owner
        owner._raise_if_aborted()
        token = credentials.get("access_token")
        if not isinstance(token, str) or not token:
            raise ValueError("Codex OAuth access token is unavailable; log in again")
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "User-Agent": f"Cloudra/{__version__}",
            "originator": "cloudra",
            "OpenAI-Beta": "responses=experimental",
        }
        for key, header in (("account_id", "ChatGPT-Account-ID"), ("residency", "x-openai-internal-codex-residency")):
            if credentials.get(key):
                headers[header] = credentials[key]
        request = self.client.build_request("POST", f"{CODEX_BASE_URL}/responses", headers=headers, json=payload)

        async def send():
            owner._raise_if_aborted()
            try:
                response = await self.client.send(request, stream=True)
            except httpx.TimeoutException as exc:
                raise openai.APITimeoutError(request=request) from exc
            except httpx.TransportError as exc:
                raise openai.APIConnectionError(request=request) from exc
            try:
                owner._raise_if_aborted()
                if response.status_code >= 300:
                    await response.aread()
                    # Provider bodies can contain credential material; keep status diagnostics safe.
                    error_type = openai.AuthenticationError if response.status_code == 401 else openai.RateLimitError if response.status_code == 429 else openai.APIStatusError
                    raise error_type(f"Codex request failed (HTTP {response.status_code})", response=response, body=None)
                return response
            except BaseException:
                await response.aclose()
                raise

        return await owner._accounted_request(send)

    async def create(self, kwargs: dict):
        owner = self.owner
        payload = _build_payload(kwargs)
        try:
            credentials = await asyncio.to_thread(resolve_codex_credentials)
            owner._raise_if_aborted()
            try:
                response = await self._send(payload, credentials)
            except openai.AuthenticationError:
                owner._raise_if_aborted()
                await owner._emit_status("llm_retry", reason="codex_oauth_refresh", attempt=1, max_retries=1, delay=0)
                credentials = await asyncio.to_thread(resolve_codex_credentials, force_refresh=True, rejected_access_token=credentials["access_token"])
                owner._raise_if_aborted()
                response = await self._send(payload, credentials)
        except Exception as exc:
            await owner._emit_status("llm_error", error=str(exc), level="codex")
            raise
        self.responses.add(response)
        state = _ResponseState()
        stream = self._stream(response, state)
        if kwargs.get("stream"):
            return stream
        async for _ in stream:
            pass
        return state.completion()

    async def _stream(self, response: httpx.Response, state: _ResponseState):
        lines = []
        try:
            async for line in response.aiter_lines():
                self.owner._raise_if_aborted()
                if line:
                    if line.startswith("data:"):
                        lines.append(line[5:].lstrip(" "))
                    continue
                if not lines:
                    continue
                data = "\n".join(lines)
                lines.clear()
                try:
                    event = json.loads(data)
                except (json.JSONDecodeError, TypeError) as exc:
                    raise RuntimeError("Malformed Codex SSE event") from exc
                if not isinstance(event, dict):
                    raise RuntimeError("Codex SSE event must be an object")
                for chunk in state.process(event):
                    yield chunk
                if state.finish:
                    self.owner._last_usage = state.usage
                    return
            raise RuntimeError("Codex SSE stream ended before its terminal response")
        except httpx.TransportError as exc:
            error = RuntimeError("Codex SSE stream disconnected before completion")
            await self.owner._emit_status("llm_error", error=str(error), level="codex")
            raise error from exc
        except Exception as exc:
            await self.owner._emit_status("llm_error", error=str(exc), level="codex")
            raise
        finally:
            self.responses.discard(response)
            await response.aclose()

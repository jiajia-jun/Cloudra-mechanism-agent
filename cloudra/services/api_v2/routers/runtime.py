"""Runtime health/capabilities and global LLM config routes."""

from __future__ import annotations

import asyncio
import os
import signal
from typing import Any

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from cloudra import __version__

from ..context import ApiContext
from ..models import GlobalConfigPatch, OpenRouterExchangeRequest


def build_router(ctx: ApiContext) -> APIRouter:
    router = APIRouter()

    @router.get("/api/v2/runtime/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @router.post("/api/v2/runtime/shutdown", dependencies=ctx.protected)
    async def runtime_shutdown() -> dict[str, str]:
        """显式全停入口（`cloudra stop` 调用）：进程内停准入（守护自愈
        失效），延迟一拍后 SIGTERM 本进程——uvicorn 走优雅 lifespan 关停
        （取消并 await 推理/收尾任务、关流/客户端、回收 JS host）。
        计算进程（scheduler/guard/QM）不受此入口影响（执行面铁律）。
        """
        from cloudra.services.daemon_supervisor import request_daemons_shutdown

        request_daemons_shutdown()
        # 先让响应发出去再关停本进程。
        asyncio.get_running_loop().call_later(
            0.5, os.kill, os.getpid(), signal.SIGTERM
        )
        return {"status": "shutting_down"}

    @router.get("/api/v2/runtime/capabilities", dependencies=ctx.protected)
    async def runtime_capabilities() -> dict[str, Any]:
        roles = [role.model_dump(mode="json") for role in ctx.core.roles.list()]
        return {
            "version": __version__,
            "roles": roles,
            "platform": "desktop",
            "strict_events": ctx.core.event_log.strict,
        }

    @router.get("/api/v2/runtime/providers", dependencies=ctx.protected)
    async def runtime_providers() -> list[dict[str, Any]]:
        """返回支持的模型供应商预设列表。"""
        from cloudra.infra.providers import list_provider_presets
        return [p.to_dict() for p in list_provider_presets()]

    @router.get("/api/v2/runtime/providers/openrouter/pkce", dependencies=ctx.protected)
    async def openrouter_pkce(callback_url: str | None = None) -> dict[str, str]:
        """生成 OpenRouter OAuth PKCE 授权链接与密钥对。"""
        from cloudra.infra.providers import get_openrouter_auth_url

        auth_url, verifier, challenge = get_openrouter_auth_url(callback_url)
        return {
            "auth_url": auth_url,
            "code_verifier": verifier,
            "code_challenge": challenge,
        }

    @router.post("/api/v2/runtime/providers/openrouter/code-exchange", dependencies=ctx.protected)
    async def openrouter_code_exchange(body: OpenRouterExchangeRequest) -> dict[str, Any]:
        """使用授权码换取 OpenRouter API Key，可选自动落盘到对应 slot。"""
        from cloudra.infra.config import mutate_config
        from cloudra.infra.providers import apply_provider_preset, exchange_openrouter_code

        key = await asyncio.to_thread(exchange_openrouter_code, body.code, body.code_verifier)

        if body.slot:
            def _apply(work) -> None:
                target = work.coordinator if body.slot == "coordinator" else work.follower
                apply_provider_preset(target, "openrouter")
                target.key = key

            await asyncio.to_thread(mutate_config, _apply)

        return {"key": key, "saved": bool(body.slot)}

    @router.get("/api/v2/runtime/providers/openrouter/callback")
    async def openrouter_callback(code: str = "") -> HTMLResponse:
        """OpenRouter OAuth 回调重定向端点：通过 postMessage 通知 opener，或重定向回应用主页。"""
        import json

        # 内联 <script> 里不能塞裸 JSON 字符串：code 是查询参数，而本端点必然
        # 未鉴权（浏览器重定向带不了 bearer），`</script>` 会提前闭合脚本元素，
        # 其后的标签直接进 DOM（实测反射型 XSS）。转义 `<` 即可——json.dumps
        # 已把非 ASCII（含 U+2028/2029）转成 \uXXXX，只剩这一处缺口。
        escaped_code = json.dumps(code).replace("<", "\\u003c")
        html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>OpenRouter 授权完成</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      margin: 0;
      background: #0f172a;
      color: #f8fafc;
    }}
    .card {{
      background: #1e293b;
      padding: 2.5rem;
      border-radius: 12px;
      box-shadow: 0 4px 12px rgba(0,0,0,0.3);
      text-align: center;
      max-width: 420px;
    }}
    h2 {{ color: #38bdf8; margin-top: 0; }}
    p {{ color: #94a3b8; font-size: 0.95rem; line-height: 1.5; }}
  </style>
</head>
<body>
  <div class="card">
    <h2>✓ OpenRouter 授权成功</h2>
    <p>授权已完成，正在返回 Cloudra...</p>
  </div>
  <script>
    const code = {escaped_code};
    if (window.opener) {{
      window.opener.postMessage({{ type: 'OPENROUTER_AUTH_CODE', code: code }}, window.location.origin);
      setTimeout(() => window.close(), 600);
    }} else {{
      window.location.href = '/?openrouter_code=' + encodeURIComponent(code);
    }}
  </script>
</body>
</html>"""
        return HTMLResponse(content=html)

    @router.get("/api/v2/runtime/config", dependencies=ctx.protected)
    async def runtime_config() -> dict[str, Any]:
        """Global LLM config: the fallback behind empty per-agent settings."""
        from cloudra.infra.config import get_config
        from cloudra.infra.providers import detect_provider_from_url

        cfg = get_config()

        def slot(role) -> dict[str, Any]:
            provider_id = role.provider
            if not provider_id and role.url:
                detected = detect_provider_from_url(role.url)
                provider_id = detected.id if detected else "custom"
            return {
                "provider": provider_id or "custom",
                "model": role.model,
                "url": role.url,
                "key_set": bool(role.key),
                "supports_vision": role.supports_vision,
                "context_window": role.context_window,
                "timeout": role.timeout,
                "reasoning_effort": role.reasoning_effort,
            }

        return {
            "config_file": str(cfg.config_file),
            "coordinator": slot(cfg.coordinator),
            "follower": slot(cfg.follower),
        }

    @router.patch("/api/v2/runtime/config", dependencies=ctx.protected)
    async def patch_runtime_config(body: GlobalConfigPatch) -> dict[str, Any]:
        """Update one global LLM slot and persist it to the YAML config.

        Writes go through ``mutate_config``: the disk YAML is the source of
        truth, and the in-memory singleton (what empty per-agent settings
        fall back to via adapters.legacy_default_settings) is refreshed from
        disk in the same critical section, so the change is live on the next
        LLM request.  ``key=""`` clears the stored key; keys are write-only
        and never returned by the GET endpoint.
        """
        from cloudra.infra.config import mutate_config
        from cloudra.infra.providers import apply_provider_preset, detect_provider_from_url

        slot = body.slot
        changes = body.changes.model_dump(exclude_unset=True)

        def _apply(work) -> None:
            target = work.coordinator if slot == "coordinator" else work.follower
            if "provider" in changes and changes["provider"]:
                apply_provider_preset(target, changes["provider"])
            for field, value in changes.items():
                setattr(target, field, value)
            if "url" in changes and "provider" not in changes:
                detected = detect_provider_from_url(target.url)
                if detected:
                    target.provider = detected.id

        await asyncio.to_thread(mutate_config, _apply)
        return await runtime_config()

    return router

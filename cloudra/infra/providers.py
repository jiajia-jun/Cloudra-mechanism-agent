"""常见 LLM 模型供应商预设（Provider Presets）。

支持 OpenRouter、OpenCode Go、DeepSeek、OpenAI、Google Gemini、
阿里通义千问、硅基流动、月之暗面 (Kimi)、智谱 AI (GLM)、本地 Ollama 等
主流供应商的默认 API 端点、推荐模型及推荐参数。
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import threading
import time
import urllib.parse
from collections.abc import Callable
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import urlsplit

import requests


@dataclass(frozen=True)
class ProviderPreset:
    """单个模型供应商预设信息。"""

    id: str
    name: str
    default_url: str
    default_model: str
    models: list[str]
    context_window: int = 128000
    supports_vision: bool = True
    native_search: str = "auto"
    key_hint: str = ""
    match_hosts: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_BUILTIN_PROVIDERS: list[ProviderPreset] = [
    ProviderPreset(
        id="openrouter",
        name="OpenRouter",
        default_url="https://openrouter.ai/api/v1",
        default_model="anthropic/claude-sonnet-5",
        models=[
            "anthropic/claude-sonnet-5",
            "anthropic/claude-opus-5",
            "openai/gpt-6-astra",
            "openai/gpt-6-astra-pro",
            "deepseek/deepseek-v4-pro",
            "deepseek/deepseek-v4-flash",
            "google/gemini-3.8-flash",
            "google/gemini-3.7-flash",
            "qwen/qwen3.8-max-0902",
            "qwen/qwen3.8-flash",
            "moonshotai/kimi-k3",
            "z-ai/glm-5.3",
        ],
        context_window=1000000,
        supports_vision=True,
        native_search="openrouter",
        key_hint="sk-or-v1-...",
        match_hosts=("openrouter.ai",),
    ),
    ProviderPreset(
        id="opencode_go",
        name="OpenCode Go",
        default_url="https://opencode.ai/zen/go/v1",
        default_model="deepseek-v4-pro",
        models=[
            "deepseek-v4-pro",
            "deepseek-v4-flash",
            "qwen3.8-max",
            "qwen3.8-flash",
            "kimi-k3",
            "kimi-k2.7-code",
            "glm-5.3",
            "glm-5.3-flash",
            "minimax-m3",
            "gpt-5.6-luna",
        ],
        context_window=1000000,
        supports_vision=True,
        native_search="auto",
        key_hint="sk-...",
        match_hosts=("opencode.ai",),
    ),
    ProviderPreset(
        id="deepseek",
        name="DeepSeek (官方)",
        default_url="https://api.deepseek.com",
        default_model="deepseek-v4-pro",
        models=[
            "deepseek-v4-pro",
            "deepseek-v4-flash",
            "deepseek-chat",
            "deepseek-reasoner",
        ],
        context_window=1000000,
        supports_vision=False,
        native_search="deepseek",
        key_hint="sk-...",
        match_hosts=("api.deepseek.com", "deepseek.com"),
    ),
    ProviderPreset(
        id="openai",
        name="OpenAI",
        default_url="https://api.openai.com/v1",
        default_model="gpt-6-astra",
        models=[
            "gpt-6-astra",
            "gpt-6-astra-pro",
            "gpt-5.6-luna",
            "o3",
            "o3-mini",
        ],
        context_window=1050000,
        supports_vision=True,
        native_search="auto",
        key_hint="sk-proj-...",
        match_hosts=("api.openai.com",),
    ),
    ProviderPreset(
        id="gemini",
        name="Google Gemini",
        default_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        default_model="gemini-3.8-flash",
        models=[
            "gemini-3.8-flash",
            "gemini-3.7-flash",
            "gemini-3.5-flash-lite",
        ],
        context_window=1048576,
        supports_vision=True,
        native_search="auto",
        key_hint="AIzaSy...",
        match_hosts=("generativelanguage.googleapis.com", "googleapis.com"),
    ),
    ProviderPreset(
        id="dashscope",
        name="阿里通义千问 (DashScope)",
        default_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        default_model="qwen3.8-max",
        models=[
            "qwen3.8-max",
            "qwen3.8-flash",
            "qwen3.7-max",
            "qwen3.7-plus",
            "qwen-max",
            "qwen-plus",
        ],
        context_window=1000000,
        supports_vision=True,
        native_search="auto",
        key_hint="sk-...",
        match_hosts=("dashscope.aliyuncs.com",),
    ),
    ProviderPreset(
        id="siliconflow",
        name="硅基流动 (SiliconFlow)",
        default_url="https://api.siliconflow.cn/v1",
        default_model="deepseek-ai/DeepSeek-V4-Pro",
        models=[
            "deepseek-ai/DeepSeek-V4-Pro",
            "deepseek-ai/DeepSeek-V4-Flash",
            "Qwen/Qwen3.8-Max",
            "Qwen/Qwen3.8-27B",
            "THUDM/glm-5.3",
            "deepseek-ai/DeepSeek-V3",
        ],
        context_window=1000000,
        supports_vision=True,
        native_search="auto",
        key_hint="sk-...",
        match_hosts=("api.siliconflow.cn",),
    ),
    ProviderPreset(
        id="moonshot",
        name="Moonshot (Kimi 开放平台)",
        default_url="https://api.moonshot.cn/v1",
        default_model="kimi-k3",
        models=[
            "kimi-k3",
            "kimi-k2.7-code",
            "kimi-k2.6",
            "kimi-latest",
        ],
        context_window=1048576,
        supports_vision=True,
        native_search="auto",
        key_hint="sk-...",
        match_hosts=("api.moonshot.cn", "api.moonshot.ai", "moonshot.cn", "moonshot.ai"),
    ),
    ProviderPreset(
        id="kimi_coding",
        name="Kimi Coding Plan (Kimi Code)",
        default_url="https://api.kimi.com/coding/v1",
        default_model="kimi-for-coding",
        models=[
            "kimi-for-coding",
            "kimi-for-coding-highspeed",
            "k3",
            "k3-256k",
        ],
        context_window=1048576,
        supports_vision=True,
        native_search="auto",
        key_hint="sk-kimi-...",
        match_hosts=("api.kimi.com",),
    ),
    ProviderPreset(
        id="zhipu",
        name="智谱 AI (GLM)",
        default_url="https://open.bigmodel.cn/api/paas/v4",
        default_model="glm-5.3",
        models=[
            "glm-5.3",
            "glm-5.3-flash",
            "glm-5.2",
            "glm-latest",
            "glm-flash-latest",
        ],
        context_window=1310720,
        supports_vision=True,
        native_search="auto",
        key_hint="...",
        match_hosts=("open.bigmodel.cn", "bigmodel.cn"),
    ),
    ProviderPreset(
        id="minimax",
        name="MiniMax",
        default_url="https://api.minimaxi.com/v1",
        default_model="minimax-m3",
        models=[
            "minimax-m3",
            "minimax-m2.7",
            "minimax-m2.5",
        ],
        context_window=1048576,
        supports_vision=True,
        native_search="auto",
        key_hint="sk-...",
        match_hosts=("api.minimaxi.com", "api.minimax.chat"),
    ),
    ProviderPreset(
        id="ollama",
        name="Ollama (本地)",
        default_url="http://localhost:11434/v1",
        default_model="deepseek-v4",
        models=[
            "deepseek-v4",
            "qwen3.8:27b",
            "llama-4:scout",
            "llama-4:maverick",
        ],
        context_window=128000,
        supports_vision=True,
        native_search="off",
        key_hint="无需 Key",
        match_hosts=("localhost:11434", "127.0.0.1:11434"),
    ),
    ProviderPreset(
        id="custom",
        name="自定义 (Custom)",
        default_url="",
        default_model="",
        models=[],
        context_window=128000,
        supports_vision=True,
        native_search="auto",
        key_hint="输入 API Key",
        match_hosts=(),
    ),
]

_ALIASES: dict[str, str] = {
    "opencode": "opencode_go",
    "opencode-go": "opencode_go",
    "opencodego": "opencode_go",
    "qwen": "dashscope",
    "tongyi": "dashscope",
    "kimi": "moonshot",
    "kimi-coding": "kimi_coding",
    "kimicoding": "kimi_coding",
    "codingplan": "kimi_coding",
    "coding-plan": "kimi_coding",
    "kimi-coding-plan": "kimi_coding",
    "kimi_coding_plan": "kimi_coding",
    "kimi_code": "kimi_coding",
    "kimi-code": "kimi_coding",
    "glm": "zhipu",
    "bigmodel": "zhipu",
    "google": "gemini",
    "minimax": "minimax",
}


def list_provider_presets() -> list[ProviderPreset]:
    """返回所有内置供应商预设列表。"""
    return list(_BUILTIN_PROVIDERS)


def get_provider_preset(id_or_alias: str) -> ProviderPreset | None:
    """根据 ID 或别名查询供应商预设。"""
    if not id_or_alias:
        return None
    key = id_or_alias.strip().lower()
    canonical = _ALIASES.get(key, key)
    for p in _BUILTIN_PROVIDERS:
        if p.id == canonical:
            return p
    return None


def detect_provider_from_url(url: str) -> ProviderPreset | None:
    """根据 base_url 主机名与路径智能反向匹配供应商预设。"""
    if not url:
        return None
    url_lower = url.lower()
    # 特殊专一路径优先判定：Kimi Coding Plan
    if "api.kimi.com/coding" in url_lower or "kimi.com/coding" in url_lower:
        return get_provider_preset("kimi_coding")

    try:
        parsed = urlsplit(url if "://" in url else f"//{url}")
        host = (parsed.netloc or parsed.path.split("/")[0] or "").lower()
        host_without_port = host.split(":")[0]
    except Exception:
        return None

    for p in _BUILTIN_PROVIDERS:
        for m in p.match_hosts:
            if m.lower() in host or m.lower() in host_without_port:
                return p
    return None


def apply_provider_preset(
    target: Any,
    provider_id: str,
    overwrite_model: bool = False,
) -> bool:
    """将 provider 预设应用到 LLMConfig 或 dict 目标对象。

    Args:
        target: 目标对象（具有 url, model, context_window 等属性或字段）
        provider_id: 供应商 ID 或别名
        overwrite_model: 若为 True，强制将 model 改为预设 default_model；
            若为 False，仅在当前 model 为空或为其它默认占位时覆盖。

    Returns:
        是否成功匹配并应用。
    """
    preset = get_provider_preset(provider_id)
    if preset is None or preset.id == "custom":
        return False

    is_dict = isinstance(target, dict)

    def _get(field: str, default: Any = None) -> Any:
        if is_dict:
            return target.get(field, default)
        return getattr(target, field, default)

    def _set(field: str, val: Any) -> None:
        if is_dict:
            target[field] = val
        elif hasattr(target, field):
            setattr(target, field, val)

    _set("provider", preset.id)
    if preset.default_url:
        _set("url", preset.default_url)

    curr_model = _get("model", "")
    _legacy_or_default_models = {
        "deepseek-4-pro",
        "deepseek-v4-pro",
        "deepseek-chat",
        "gpt-4o",
        "anthropic/claude-3.7-sonnet",
        "moonshot-v1-128k",
        "glm-4-plus",
        "qwen-plus",
        "deepseek-ai/DeepSeek-V3",
        "kimi-for-coding",
    }
    if overwrite_model or not curr_model or curr_model in _legacy_or_default_models:
        if preset.default_model:
            _set("model", preset.default_model)

    if preset.context_window:
        _set("context_window", preset.context_window)
    _set("supports_vision", preset.supports_vision)
    if preset.native_search != "auto":
        _set("native_search", preset.native_search)

    return True


def generate_pkce_pair() -> tuple[str, str]:
    """生成 OAuth 2.0 PKCE 的 code_verifier 与 code_challenge (S256)。"""
    token = secrets.token_bytes(32)
    verifier = base64.urlsafe_b64encode(token).decode("utf-8").rstrip("=")
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")
    return verifier, challenge


def get_openrouter_auth_url(callback_url: str | None = None) -> tuple[str, str, str]:
    """构建 OpenRouter 账号授权链接。

    Returns:
        (auth_url, code_verifier, code_challenge)
    """
    verifier, challenge = generate_pkce_pair()
    params = {
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    if callback_url:
        params["callback_url"] = callback_url
    query = urllib.parse.urlencode(params)
    auth_url = f"https://openrouter.ai/auth?{query}"
    return auth_url, verifier, challenge


def exchange_openrouter_code(code: str, code_verifier: str) -> str:
    """使用授权码换取 OpenRouter API Key。"""
    url = "https://openrouter.ai/api/v1/auth/keys"
    payload = {
        "code": code,
        "code_verifier": code_verifier,
        "code_challenge_method": "S256",
    }
    resp = requests.post(url, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    key = data.get("key")
    if not key:
        raise ValueError(f"OpenRouter 授权交换未返回 key: {data}")
    return str(key)


def run_local_auth_listener(timeout: float = 120.0) -> tuple[str, Callable[[float], str | None]]:
    """启动本地临时 HTTP 监听服务，用于捕获 OpenRouter OAuth 重定向的 code。

    Returns:
        (callback_url, wait_for_code_fn)
    """
    captured_code: list[str | None] = [None]
    done_event = threading.Event()

    class _CallbackHandler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def do_GET(self):
            parsed = urllib.parse.urlsplit(self.path)
            query = urllib.parse.parse_qs(parsed.query)
            if "code" in query and query["code"]:
                captured_code[0] = query["code"][0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                response_html = """<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Cloudra 授权成功</title>
<style>
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; background: #0f172a; color: #f8fafc; }
.box { background: #1e293b; padding: 2.5rem; border-radius: 12px; text-align: center; max-width: 440px; box-shadow: 0 4px 12px rgba(0,0,0,0.3); }
h2 { color: #38bdf8; margin-top: 0; }
p { color: #94a3b8; line-height: 1.5; }
</style>
</head>
<body>
<div class="box">
  <h2>✓ OpenRouter 授权成功</h2>
  <p>Cloudra CLI 已自动接收授权并绑定 API Key。<br>您可以关闭此页面返回终端。</p>
</div>
<script>setTimeout(() => window.close(), 1200);</script>
</body>
</html>"""
                self.wfile.write(response_html.encode("utf-8"))
            else:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Missing code query parameter.")
            done_event.set()

    server = HTTPServer(("127.0.0.1", 0), _CallbackHandler)
    server.timeout = 1.0
    port = server.server_port
    callback_url = f"http://127.0.0.1:{port}/callback"

    def _serve():
        start_time = time.time()
        while not done_event.is_set():
            if time.time() - start_time > timeout:
                break
            server.handle_request()
        server.server_close()

    thread = threading.Thread(target=_serve, daemon=True)
    thread.start()

    def _wait_for_code(wait_time: float = timeout) -> str | None:
        done_event.wait(timeout=wait_time)
        return captured_code[0]

    return callback_url, _wait_for_code

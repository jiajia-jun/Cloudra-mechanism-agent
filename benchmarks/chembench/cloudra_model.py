"""
Cloudra model adapter for ChemBench via LiteLLM custom provider.

ChemBench internally wraps every model string with ``ChemBenchModel``, which
calls ``litellm.batch_completion``. To use an OpenAI-compatible endpoint that
is not natively supported by LiteLLM (such as MiMo), we register a custom
LiteLLM provider. The returned model name (e.g. ``cloudra/cloudra-mimo``) can
then be passed to ``PrompterBuilder.from_model_object``.
"""

from __future__ import annotations

import os
import time
from typing import Any

import litellm
from openai import OpenAI


# Default system prompt used to enforce the [ANSWER] format ChemBench expects.
DEFAULT_SYSTEM_PROMPT = (
    "You are a helpful chemistry assistant. Answer the following question "
    "concisely. Report your final answer inside [ANSWER]...[/ANSWER] tags."
)

_PROVIDER_NAME = "cloudra"


class CloudraLiteLLM(litellm.CustomLLM):
    """LiteLLM custom handler backed by a synchronous OpenAI-compatible client."""

    def __init__(
        self,
        model: str | None = None,
        url: str | None = None,
        api_key: str | None = None,
        system_prompt: str | None = None,
        timeout: float = 120.0,
        **default_kwargs: Any,
    ) -> None:
        super().__init__()
        self.model = model or _default_model()
        self.url = url or _default_url()
        self.api_key = api_key or _default_api_key() or os.getenv("OPENAI_API_KEY", "")
        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        self.timeout = timeout
        self.default_kwargs = default_kwargs

        self._client = OpenAI(
            base_url=self.url,
            api_key=self.api_key,
            timeout=self.timeout,
        )

    def _prepare_messages(self, messages: list[dict[str, str]]) -> list[dict[str, str]]:
        """Ensure a system message with our formatting instructions exists."""
        if messages and messages[0].get("role") == "system":
            return [{"role": "system", "content": self.system_prompt}, *messages[1:]]
        return [{"role": "system", "content": self.system_prompt}, *messages]

    def completion(self, messages: list[dict[str, str]], **kwargs: Any) -> litellm.ModelResponse:
        """Single completion required by LiteLLM custom provider API."""
        merged = {**self.default_kwargs, **kwargs}
        response = self._client.chat.completions.create(
            model=self.model,
            messages=self._prepare_messages(messages),
            temperature=merged.get("temperature", 0.0),
            max_tokens=merged.get("max_tokens", 2048),
            timeout=merged.get("timeout", self.timeout),
        )
        return _format_response(response.choices[0].message.content or "")

    def batch_completion(
        self, messages_list: list[list[dict[str, str]]], **kwargs: Any
    ) -> list[litellm.ModelResponse]:
        """Batch completion required by ChemBench / LiteLLM batch path."""
        import time
        results = []
        for i, messages in enumerate(messages_list):
            if i > 0:
                # Add a small delay between requests to avoid rate limiting
                time.sleep(0.5)
            results.append(self.completion(messages, **kwargs))
        return results


def _format_response(text: str) -> litellm.ModelResponse:
    """Wrap raw text in a LiteLLM ModelResponse."""
    return litellm.ModelResponse(
        id=f"cmpl-{int(time.time())}",
        object="chat.completion",
        created=int(time.time()),
        model="cloudra",
        choices=[
            litellm.Choices(
                index=0,
                finish_reason="stop",
                message=litellm.Message(content=text, role="assistant"),
            )
        ],
        usage={
            "prompt_tokens": 0,
            "completion_tokens": len(text.split()),
            "total_tokens": len(text.split()),
        },
    )


def _default_model() -> str:
    try:
        from cloudra.config import get_config

        return get_config().coordinator.model
    except Exception:
        return os.getenv("COORDINATOR_MODEL", "mimo-v2.5-ultraspeed")


def _default_url() -> str:
    try:
        from cloudra.config import get_config

        return get_config().coordinator.url
    except Exception:
        return os.getenv("COORDINATOR_URL", "https://api.xiaomimimo.com/v1")


def _default_api_key() -> str:
    try:
        from cloudra.config import get_config

        return get_config().coordinator.key
    except Exception:
        return os.getenv("COORDINATOR_KEY", "")


def build_model(
    model: str | None = None,
    url: str | None = None,
    api_key: str | None = None,
    **kwargs: Any,
) -> str:
    """Register the Cloudra custom provider and return the LiteLLM model name.

    The returned string can be passed directly to
    ``chembench.prompter.PrompterBuilder.from_model_object``.
    """
    handler = CloudraLiteLLM(
        model=model or _default_model(),
        url=url or _default_url(),
        api_key=api_key or _default_api_key(),
        **kwargs,
    )

    # Register (or re-register) the custom provider for this process.
    litellm.custom_provider_map = [
        {"provider": _PROVIDER_NAME, "custom_handler": handler}
    ]
    return f"{_PROVIDER_NAME}/cloudra-model"

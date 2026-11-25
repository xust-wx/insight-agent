"""DashScope OpenAI-compatible client with direct domestic connection (trust_env=False)."""

from __future__ import annotations

from typing import Any

import httpx
from openai import AsyncOpenAI, OpenAI

from insight_agent.config import Settings, get_settings


class DashScopeClient:
    """Wrapper around OpenAI SDK targeting Alibaba Cloud Bailian (DashScope).

    Key engineering guarantees (ADR-001):
    - Uses httpx.Client(trust_env=False) to bypass local overseas system proxies.
    - Always passes encoding_format="float" and dimensions=settings.embedding_dim for embeddings.
    - Supports node-level reasoning effort control for qwen4-max.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        if not self.settings.dashscope_api_key:
            raise ValueError(
                "DASHSCOPE_API_KEY is not configured. Please set it in .env before calling LLM APIs."
            )

        self._sync_http = httpx.Client(trust_env=False, timeout=60.0)
        self._async_http = httpx.AsyncClient(trust_env=False, timeout=60.0)

        self.sync_client = OpenAI(
            api_key=self.settings.dashscope_api_key,
            base_url=self.settings.dashscope_base_url,
            http_client=self._sync_http,
            max_retries=3,
        )
        self.async_client = AsyncOpenAI(
            api_key=self.settings.dashscope_api_key,
            base_url=self.settings.dashscope_base_url,
            http_client=self._async_http,
            max_retries=3,
        )

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        reasoning_effort: str | None = None,
        max_completion_tokens: int | None = None,
        temperature: float = 0.0,
        extra_body: dict[str, Any] | None = None,
    ) -> Any:
        """Synchronous chat completion call."""
        kwargs: dict[str, Any] = {
            "model": self.settings.llm_model,
            "messages": messages,
            "temperature": temperature,
        }
        if reasoning_effort:
            kwargs["reasoning_effort"] = reasoning_effort
        if max_completion_tokens is not None:
            kwargs["max_completion_tokens"] = max_completion_tokens
        if extra_body:
            kwargs["extra_body"] = extra_body
        return self.sync_client.chat.completions.create(**kwargs)

    def embed_texts(self, texts: list[str], *, batch_size: int = 10) -> list[list[float]]:
        """Generate float embeddings with explicit encoding_format='float' and fixed dimension."""
        if not texts:
            return []
        all_vectors: list[list[float]] = []
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            resp = self.sync_client.embeddings.create(
                model=self.settings.embedding_model,
                input=batch,
                dimensions=self.settings.embedding_dim,
                encoding_format="float",
            )
            sorted_items = sorted(resp.data, key=lambda x: x.index)
            for item in sorted_items:
                vec = item.embedding
                if len(vec) != self.settings.embedding_dim:
                    raise ValueError(
                        f"Expected embedding dim {self.settings.embedding_dim}, got {len(vec)}"
                    )
                all_vectors.append(vec)
        return all_vectors

    def close(self) -> None:
        self._sync_http.close()


def get_llm_client(settings: Settings | None = None) -> DashScopeClient:
    return DashScopeClient(settings=settings)

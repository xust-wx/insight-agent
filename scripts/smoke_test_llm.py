"""S1 Entry Smoke Test: Verify DashScope direct connection, qwen4-max, and 1024-d float embeddings."""

from __future__ import annotations

import json
import sys
import time

from insight_agent.config import get_settings
from insight_agent.llm.client import DashScopeClient


def main() -> int:
    settings = get_settings()
    print("=== Insight Agent S1 LLM & Embedding Smoke Test ===")
    print(f"Base URL        : {settings.dashscope_base_url}")
    print(f"LLM Model       : {settings.llm_model}")
    print(f"Embedding Model : {settings.embedding_model} (dim={settings.embedding_dim})")
    print(f"API Key Set     : {'YES' if bool(settings.dashscope_api_key) else 'NO'}")

    if not settings.dashscope_api_key:
        print(
            "\n[BLOCKED] DASHSCOPE_API_KEY is empty in .env. "
            "Please fill in your Alibaba Cloud Bailian API key and re-run."
        )
        return 2

    client = DashScopeClient(settings)
    try:
        # 1. Test Chat Completion with fast reasoning_effort
        print("\n[1/3] Testing Chat Completion (fast mode)...")
        t0 = time.perf_counter()
        try:
            resp = client.chat(
                messages=[
                    {"role": "system", "content": "You are a concise assistant."},
                    {"role": "user", "content": "请仅回复 JSON: {\"status\": \"ok\"}"},
                ],
                reasoning_effort=settings.llm_reasoning_effort_fast,
                max_completion_tokens=128,
            )
            mode_used = f"reasoning_effort={settings.llm_reasoning_effort_fast}"
        except Exception as exc:
            print(f"  [WARN] reasoning_effort parameter failed ({exc}); retrying without it...")
            resp = client.chat(
                messages=[
                    {"role": "system", "content": "You are a concise assistant."},
                    {"role": "user", "content": "请仅回复 JSON: {\"status\": \"ok\"}"},
                ],
                max_completion_tokens=128,
            )
            mode_used = "default (no reasoning_effort)"

        dt_ms = int((time.perf_counter() - t0) * 1000)
        msg = resp.choices[0].message
        usage = resp.usage.model_dump() if resp.usage else {}
        print(f"  OK ({dt_ms} ms) | mode={mode_used} | model={resp.model}")
        print(f"  Content : {msg.content!r}")
        print(f"  Usage   : {json.dumps(usage, ensure_ascii=False)}")

        # 2. Test Embedding (1024-d float)
        print("\n[2/3] Testing Embedding (encoding_format='float')...")
        t1 = time.perf_counter()
        vecs = client.embed_texts(["有效商品成交额 GMV（不含运费）", "订单延迟交付率与差评率"])
        dt_emb_ms = int((time.perf_counter() - t1) * 1000)
        print(
            f"  OK ({dt_emb_ms} ms) | count={len(vecs)} | dim={len(vecs[0])} | "
            f"sample={vecs[0][:3]}"
        )

        # 3. Verify vector cosine similarity sanity
        dot = sum(a * b for a, b in zip(vecs[0], vecs[1], strict=True))
        norm0 = sum(a * a for a in vecs[0]) ** 0.5
        norm1 = sum(b * b for b in vecs[1]) ** 0.5
        cos_sim = dot / (norm0 * norm1)
        print(f"\n[3/3] Cosine similarity sanity check: {cos_sim:.4f}")
        print("\n[PASS] DashScope LLM & Embedding smoke test succeeded.")
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())

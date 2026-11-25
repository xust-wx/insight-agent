"""S1 Semantic Index Builder: Populate agent_state.semantic_documents via agent_service role.

Features (closes P0-3, P1-1, P1-3, P1-5, P2-4):
- Connects via non-superuser `agent_service` role (`pg_service_dsn`).
- Tokenizes Chinese + English text with domain-customized `jieba` (`tsv_tokens` -> `tsvector`).
- Loads verified few-shots from `eval/few_shots/verified_sqls.yaml`.
- Includes table `COMMENT` descriptions for both `olist_clean` and 30 `olist_distractor` tables.
- Tracks SHA256 `content_hash` to skip re-embedding unchanged documents.
"""

from __future__ import annotations

import hashlib
import json
import sys
from typing import Any

import psycopg
import yaml

from insight_agent.config import get_settings
from insight_agent.llm.client import DashScopeClient
from insight_agent.semantic.tokenizer import tokenize_for_fts


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def collect_documents(conn: psycopg.Connection) -> list[dict[str, Any]]:
    settings = get_settings()
    with settings.glossary_path.open("r", encoding="utf-8") as f:
        glossary = yaml.safe_load(f)
    with settings.few_shots_path.open("r", encoding="utf-8") as f:
        few_shots_doc = yaml.safe_load(f)

    docs: list[dict[str, Any]] = []

    # 1. Metrics
    for m in glossary["metrics"]:
        content = (
            f"指标名称: {m['name']} (id={m['id']})\n"
            f"别名: {', '.join(m.get('aliases', []))}\n"
            f"定义: {m['definition']}\n"
            f"粒度: {m['grain']} | 所需表: {', '.join(m.get('required_tables', []))}\n"
            f"允许维度: {', '.join(m.get('allowed_dimensions', []))}\n"
            f"不兼容维度: {json.dumps(m.get('incompatible_dimensions', []), ensure_ascii=False)}\n"
            f"SQL模板:\n{m['sql_template'].strip()}"
        )
        docs.append(
            {
                "doc_type": "metric",
                "doc_key": f"metric:{m['id']}",
                "title": f"{m['name']} ({m['id']})",
                "content": content,
                "metadata": {
                    "metric_id": m["id"],
                    "allowed_dimensions": m.get("allowed_dimensions", []),
                },
            }
        )

    # 2. Known pitfalls
    for p in glossary.get("known_pitfalls", []):
        docs.append(
            {
                "doc_type": "pitfall",
                "doc_key": f"pitfall:{p['id']}",
                "title": p["title"],
                "content": f"{p['title']}: {p['rule']}",
                "metadata": {"pitfall_id": p["id"]},
            }
        )

    # 3. Verified Few-shot SQLs from YAML
    for fs in few_shots_doc.get("examples", []):
        docs.append(
            {
                "doc_type": "few_shot",
                "doc_key": fs["key"],
                "title": fs["title"],
                "content": f"问题：{fs['question']}\nSQL：\n{fs['sql'].strip()}",
                "metadata": {"question": fs["question"]},
            }
        )

    # 4. Table schemas + PostgreSQL table comments (olist_clean + olist_distractor)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                c.table_schema,
                c.table_name,
                COALESCE(obj_description((quote_ident(c.table_schema) || '.' || quote_ident(c.table_name))::regclass), '') AS tbl_comment,
                string_agg(c.column_name || ' ' || c.data_type, ', ' ORDER BY c.ordinal_position) AS cols
            FROM information_schema.columns c
            WHERE c.table_schema IN ('olist_clean', 'olist_distractor')
            GROUP BY c.table_schema, c.table_name
            ORDER BY c.table_schema, c.table_name;
            """
        )
        for schema, tbl, tbl_comment, cols in cur.fetchall():
            desc = f"说明：{tbl_comment}\n" if tbl_comment else ""
            docs.append(
                {
                    "doc_type": "table_schema",
                    "doc_key": f"table:{schema}.{tbl}",
                    "title": f"{schema}.{tbl} {tbl_comment}".strip(),
                    "content": f"表 {schema}.{tbl}\n{desc}字段：{cols}",
                    "metadata": {"schema": schema, "table": tbl, "comment": tbl_comment},
                }
            )
    return docs


def main() -> int:
    settings = get_settings()
    has_key = bool(settings.dashscope_api_key)

    with psycopg.connect(settings.pg_service_dsn) as conn:
        docs = collect_documents(conn)
        active_keys = [d["doc_key"] for d in docs]

        # Remove stale documents no longer in source configs
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM agent_state.semantic_documents WHERE NOT (doc_key = ANY(%s));",
                (active_keys,),
            )
            cur.execute(
                """
                SELECT doc_key, content_hash, (embedding IS NOT NULL) AS has_emb
                FROM agent_state.semantic_documents;
                """
            )
            existing = {r[0]: (r[1], bool(r[2])) for r in cur.fetchall()}

        to_embed_indices: list[int] = []
        for idx, doc in enumerate(docs):
            full_text = f"{doc['title']}\n{doc['content']}"
            doc["tsv_tokens"] = tokenize_for_fts(full_text)
            doc["content_hash"] = sha256_text(full_text)
            prev = existing.get(doc["doc_key"])
            if not prev or prev[0] != doc["content_hash"] or not prev[1]:
                to_embed_indices.append(idx)

        print(
            f"Collected {len(docs)} semantic docs via role '{settings.pg_service_user}'; "
            f"{len(to_embed_indices)} need embedding ({len(docs) - len(to_embed_indices)} cached)."
        )

        new_vectors: dict[int, list[float]] = {}
        if to_embed_indices and has_key:
            client = DashScopeClient(settings)
            try:
                texts_to_embed = [f"{docs[i]['title']}\n{docs[i]['content']}" for i in to_embed_indices]
                vecs = client.embed_texts(texts_to_embed, batch_size=10)
                for i, v in zip(to_embed_indices, vecs, strict=True):
                    new_vectors[i] = v
            finally:
                client.close()

        with conn.cursor() as cur:
            for idx, doc in enumerate(docs):
                vec = new_vectors.get(idx)
                vec_str = None if vec is None else "[" + ",".join(f"{x:.8f}" for x in vec) + "]"
                cur.execute(
                    """
                    INSERT INTO agent_state.semantic_documents
                        (doc_type, doc_key, title, content, tsv_tokens, content_hash, metadata, embedding, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::vector, NOW())
                    ON CONFLICT (doc_key) DO UPDATE SET
                        doc_type = EXCLUDED.doc_type,
                        title = EXCLUDED.title,
                        content = EXCLUDED.content,
                        tsv_tokens = EXCLUDED.tsv_tokens,
                        content_hash = EXCLUDED.content_hash,
                        metadata = EXCLUDED.metadata,
                        embedding = COALESCE(EXCLUDED.embedding, agent_state.semantic_documents.embedding),
                        updated_at = NOW();
                    """,
                    (
                        doc["doc_type"],
                        doc["doc_key"],
                        doc["title"],
                        doc["content"],
                        doc["tsv_tokens"],
                        doc["content_hash"],
                        json.dumps(doc["metadata"], ensure_ascii=False),
                        vec_str,
                    ),
                )
        conn.commit()

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT doc_type, COUNT(*) AS total, COUNT(embedding) AS embedded
                FROM agent_state.semantic_documents
                GROUP BY doc_type
                ORDER BY doc_type;
                """
            )
            for dtype, total, emb in cur.fetchall():
                print(f"  - {dtype:14s}: total={total:3d}, embedded={emb:3d}")

    if not has_key and to_embed_indices:
        print("\n[BLOCKED] DASHSCOPE_API_KEY missing for new embeddings.")
        return 2
    print("\n[PASS] Jieba FTS + pgvector(1024) hybrid index built successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

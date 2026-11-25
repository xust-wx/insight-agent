"""Hybrid Retriever combining Jieba+PostgreSQL tsvector FTS and pgvector cosine similarity via RRF."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import psycopg

from insight_agent.config import Settings, get_settings
from insight_agent.llm.client import DashScopeClient
from insight_agent.semantic.tokenizer import build_or_tsquery


@dataclass(slots=True)
class RetrievedDoc:
    doc_key: str
    doc_type: str
    title: str
    content: str
    metadata: dict[str, Any]
    score: float
    fts_rank: int | None = None
    vec_rank: int | None = None


class HybridRetriever:
    """Executes keyword FTS, dense vector search, and Reciprocal Rank Fusion (RRF) via agent_service."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def fts_search(
        self,
        query: str,
        *,
        doc_types: list[str] | None = None,
        top_k: int = 10,
    ) -> list[RetrievedDoc]:
        tsq = build_or_tsquery(query)
        if not tsq:
            return []

        type_filter = "AND doc_type = ANY(%s)" if doc_types else ""
        params: list[Any] = [tsq, tsq]
        if doc_types:
            params.append(doc_types)
        params.append(top_k)

        sql = f"""
            SELECT doc_key, doc_type, title, content, metadata,
                   ts_rank_cd(tsv, to_tsquery('simple', %s)) AS rank_score
            FROM agent_state.semantic_documents
            WHERE tsv @@ to_tsquery('simple', %s)
              {type_filter}
            ORDER BY rank_score DESC, doc_key ASC
            LIMIT %s;
        """
        with psycopg.connect(self.settings.pg_service_dsn) as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

        return [
            RetrievedDoc(
                doc_key=r[0],
                doc_type=r[1],
                title=r[2],
                content=r[3],
                metadata=r[4] or {},
                score=float(r[5]),
                fts_rank=idx + 1,
            )
            for idx, r in enumerate(rows)
        ]

    def vector_search(
        self,
        query_embedding: list[float],
        *,
        doc_types: list[str] | None = None,
        top_k: int = 10,
    ) -> list[RetrievedDoc]:
        vec_literal = "[" + ",".join(f"{x:.8f}" for x in query_embedding) + "]"
        type_filter = "AND doc_type = ANY(%s)" if doc_types else ""
        params: list[Any] = [vec_literal]
        if doc_types:
            params.append(doc_types)
        params.extend([vec_literal, top_k])

        sql = f"""
            SELECT doc_key, doc_type, title, content, metadata,
                   (1.0 - (embedding <=> %s::vector)) AS cos_sim
            FROM agent_state.semantic_documents
            WHERE embedding IS NOT NULL
              {type_filter}
            ORDER BY embedding <=> %s::vector ASC
            LIMIT %s;
        """
        with psycopg.connect(self.settings.pg_service_dsn) as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

        return [
            RetrievedDoc(
                doc_key=r[0],
                doc_type=r[1],
                title=r[2],
                content=r[3],
                metadata=r[4] or {},
                score=float(r[5]),
                vec_rank=idx + 1,
            )
            for idx, r in enumerate(rows)
        ]

    def hybrid_search(
        self,
        query: str,
        *,
        doc_types: list[str] | None = None,
        top_k: int = 5,
        candidate_pool: int = 20,
        rrf_k: int = 60,
        llm_client: DashScopeClient | None = None,
    ) -> list[RetrievedDoc]:
        """Fuse Jieba+tsvector FTS and pgvector cosine rankings via RRF (1/(k+rank))."""
        fts_hits = self.fts_search(query, doc_types=doc_types, top_k=candidate_pool)

        owns_client = False
        if llm_client is None:
            llm_client = DashScopeClient(self.settings)
            owns_client = True
        try:
            q_vec = llm_client.embed_texts([query])[0]
        finally:
            if owns_client:
                llm_client.close()

        vec_hits = self.vector_search(q_vec, doc_types=doc_types, top_k=candidate_pool)

        merged: dict[str, RetrievedDoc] = {}
        rrf_scores: dict[str, float] = {}

        for doc in fts_hits:
            merged[doc.doc_key] = doc
            rrf_scores[doc.doc_key] = rrf_scores.get(doc.doc_key, 0.0) + 1.0 / (
                rrf_k + (doc.fts_rank or candidate_pool)
            )

        for doc in vec_hits:
            if doc.doc_key in merged:
                merged[doc.doc_key].vec_rank = doc.vec_rank
            else:
                merged[doc.doc_key] = doc
            rrf_scores[doc.doc_key] = rrf_scores.get(doc.doc_key, 0.0) + 1.0 / (
                rrf_k + (doc.vec_rank or candidate_pool)
            )

        ranked = sorted(
            merged.values(),
            key=lambda d: (rrf_scores[d.doc_key], -(d.vec_rank or 999), -(d.fts_rank or 999)),
            reverse=True,
        )
        for d in ranked:
            d.score = round(rrf_scores[d.doc_key], 6)
        return ranked[:top_k]

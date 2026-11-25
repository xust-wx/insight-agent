"""L3 integration tests for S1 hardened data layer, 3-tier roles, and Chinese hybrid retrieval."""

from __future__ import annotations

import psycopg
import pytest

from insight_agent.config import get_settings
from insight_agent.db.constants import OLIST_EXPECTED_FILES as EXPECTED_FILES
from insight_agent.db.readonly_executor import ReadonlyExecutor
from insight_agent.security.sql_guard import SQLGuardError
from insight_agent.semantic.retriever import HybridRetriever

pytestmark = pytest.mark.integration


def test_clean_tables_and_category_completeness() -> None:
    settings = get_settings()
    executor = ReadonlyExecutor(settings)
    expected_orders = EXPECTED_FILES["olist_orders_dataset.csv"][1]

    res = executor.execute("SELECT COUNT(*) AS cnt FROM olist_clean.orders")
    assert res.rows[0][0] == expected_orders

    rev_res = executor.execute(
        "SELECT COUNT(*), COUNT(DISTINCT order_id) FROM olist_clean.reviews"
    )
    assert rev_res.rows[0][0] == rev_res.rows[0][1] == 98673

    # Verify zero NULL categories and zero leftover untranslated Portuguese long names
    cat_res = executor.execute(
        """
        SELECT
            COUNT(*) FILTER (WHERE category_en IS NULL) AS null_cnt,
            COUNT(*) FILTER (WHERE category_en = 'portateis_cozinha_e_preparadores_de_alimentos') AS raw_pt_cnt,
            COUNT(*) FILTER (WHERE category_en = 'portable_kitchen_food_preparers') AS mapped_en_cnt
        FROM olist_clean.products
        """
    )
    assert cat_res.rows[0] == (0, 0, 10)


def test_three_tier_role_isolation_and_p0_1_hardening() -> None:
    settings = get_settings()

    # 1. Verify agent_service is strictly NOSUPERUSER and cannot mutate olist_clean or read olist_raw
    with psycopg.connect(settings.pg_service_dsn, autocommit=True) as svc_conn:
        row = svc_conn.execute(
            "SELECT rolsuper, rolcreatedb, rolcreaterole FROM pg_roles WHERE rolname = current_user"
        ).fetchone()
        assert row == (False, False, False), f"agent_service must not have elevated flags: {row}"

        with pytest.raises(psycopg.Error):
            svc_conn.execute("DELETE FROM olist_clean.orders WHERE order_id = 'nope'")
        with pytest.raises(psycopg.Error):
            svc_conn.execute("SELECT * FROM olist_raw.olist_orders_dataset LIMIT 1")

    # 2. Verify raw readonly_analyst connection blocks TEMP tables, pg_sleep, and writes even after SET
    with psycopg.connect(settings.pg_readonly_dsn, autocommit=True) as ro_conn:
        ro_conn.execute("SET default_transaction_read_only = off")
        with pytest.raises(psycopg.Error):
            ro_conn.execute("CREATE TEMP TABLE evil_probe (id INT)")
        with pytest.raises(psycopg.Error):
            ro_conn.execute("SELECT pg_sleep(0.05)")
        with pytest.raises(psycopg.Error):
            ro_conn.execute("DELETE FROM olist_clean.orders WHERE order_id = 'nope'")

    # 3. Verify ReadonlyExecutor blocks session SET, catalog recon, and enforces truncation flag
    executor = ReadonlyExecutor(settings)
    for bad in (
        "SET statement_timeout = 0",
        "SELECT * FROM pg_catalog.pg_roles",
        "SELECT * FROM information_schema.tables",
    ):
        with pytest.raises(SQLGuardError):
            executor.execute(bad)

    trunc_res = executor.execute("SELECT order_id FROM olist_clean.orders", max_rows=10)
    assert trunc_res.truncated is True
    assert trunc_res.row_count_returned == 10


def test_chinese_fts_and_hybrid_retrieval() -> None:
    retriever = HybridRetriever()

    # Pure Chinese keyword FTS leg (previously returned 0 hits before jieba fix!)
    for query_term, expected_key in [
        ("成交额", "metric:gmv"),
        ("逾期率", "metric:late_delivery_rate"),
        ("复购率", "metric:repurchase_rate_90d"),
        ("客单价", "metric:aov"),
        ("差评率", "metric:bad_review_rate"),
    ]:
        fts_hits = retriever.fts_search(query_term, doc_types=["metric"], top_k=5)
        hit_keys = [d.doc_key for d in fts_hits]
        assert expected_key in hit_keys, (
            f"Chinese FTS failed for '{query_term}': got {hit_keys}"
        )


@pytest.mark.llm
def test_live_hybrid_rrf_retrieval() -> None:
    retriever = HybridRetriever()
    hits = retriever.hybrid_search("已送达订单的逾期率和差评率有什么关系", top_k=5)
    top_keys = [d.doc_key for d in hits]
    assert "metric:late_delivery_rate" in top_keys or "few_shot:late_delivery_vs_bad_review" in top_keys

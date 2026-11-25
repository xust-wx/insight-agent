"""L1/L2 AST security tests covering docs/security_cases.md and S1_review P0-1 bypass vectors."""

from __future__ import annotations

import pytest

from insight_agent.security.sql_guard import (
    SQLGuardError,
    validate_readonly_sql,
    wrap_with_limit_probe,
)


@pytest.mark.parametrize(
    ("case_id", "malicious_sql"),
    [
        ("SEC-SQL-01", "SELECT 1; DROP TABLE olist_clean.orders;"),
        (
            "SEC-SQL-02",
            "WITH deleted AS (DELETE FROM olist_clean.orders RETURNING *) SELECT count(*) FROM deleted",
        ),
        (
            "SEC-SQL-02b",
            "WITH ins AS (INSERT INTO olist_clean.orders VALUES ('1') RETURNING *) SELECT * FROM ins",
        ),
        ("SEC-SQL-03", "SELECT * INTO temp_leak FROM olist_clean.customers"),
        ("SEC-SQL-04", "SELECT * FROM olist_clean.orders FOR UPDATE"),
        ("SEC-SQL-04b", "SELECT * FROM olist_clean.orders FOR SHARE"),
        ("SEC-SQL-05", "SELECT pg_sleep(60)"),
        ("SEC-SQL-05b", "SELECT pg_sleep_for('5 minutes')"),
        ("SEC-SQL-06", "SELECT pg_read_file('/etc/passwd')"),
        ("SEC-SQL-06b", "SELECT lo_import('/etc/passwd')"),
        ("SEC-SQL-07a", "SELECT * FROM pg_catalog.pg_shadow"),
        ("SEC-SQL-07b", "SELECT * FROM pg_roles"),
        ("SEC-SQL-07c", "SELECT * FROM information_schema.tables"),
        ("SEC-SQL-07d", "SELECT * FROM agent_state.user_memory"),
        ("SEC-SQL-07e", "SELECT * FROM olist_raw.olist_orders_dataset"),
        ("P0-1-SET-TIMEOUT", "SET statement_timeout = 0"),
        ("P0-1-SET-RO-OFF", "SET default_transaction_read_only = off"),
        ("P0-1-SET-CONFIG", "SELECT set_config('statement_timeout', '0', false)"),
        ("P0-1-CURR-SETTING", "SELECT current_setting('data_directory')"),
        ("P0-1-BEGIN-RW", "BEGIN READ WRITE"),
        ("P0-1-TEMP-TABLE", "CREATE TEMP TABLE t_evil (x INT)"),
        ("P0-1-DO-BLOCK", "DO $$ BEGIN PERFORM 1; END $$"),
        ("P0-1-COPY", "COPY olist_clean.orders TO STDOUT"),
    ],
)
def test_sql_guard_blocks_all_attack_vectors(case_id: str, malicious_sql: str) -> None:
    with pytest.raises(SQLGuardError):
        validate_readonly_sql(malicious_sql)


def test_sql_guard_allows_valid_analytical_queries() -> None:
    valid_cte_sql = """
    WITH monthly AS (
        SELECT DATE_TRUNC('month', o.order_purchase_timestamp)::DATE AS m,
               SUM(oi.price) AS gmv
        FROM olist_clean.orders o
        JOIN olist_clean.order_items oi ON o.order_id = oi.order_id
        GROUP BY 1
    )
    SELECT m, gmv FROM monthly ORDER BY m;
    """
    cleaned = validate_readonly_sql(valid_cte_sql)
    assert not cleaned.endswith(";")
    wrapped = wrap_with_limit_probe(valid_cte_sql, max_rows=500)
    assert wrapped.endswith("LIMIT 501")


def test_distractor_schema_toggle() -> None:
    q = "SELECT * FROM olist_distractor.orders_archive_2015 LIMIT 5"
    with pytest.raises(SQLGuardError):
        validate_readonly_sql(q, allow_distractors=False)
    assert validate_readonly_sql(q, allow_distractors=True) == q

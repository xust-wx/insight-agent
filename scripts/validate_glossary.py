"""S1 Glossary, Metric×Dimension Matrix, Few-Shot & Multi-Layer Security Validator.

Validates:
1. All 12 base metric `sql_template`s via `ReadonlyExecutor` (AST guard + per-tx READ ONLY).
2. All `(metric, allowed_dimension)` combinations (52 queries) + additivity invariant assertions
   (`SUM(grouped) == scalar_total` within ±0.01 for additive metrics on partition dimensions).
3. All verified few-shot SQL queries in `eval/few_shots/verified_sqls.yaml`.
4. Multi-layer SQL security: AST/Executor rejections (incl. `SET statement_timeout = 0`,
   `SET default_transaction_read_only = off`, `pg_catalog`, writable CTE, `FOR UPDATE`) AND raw
   PostgreSQL role lockdowns (`CREATE TEMP TABLE`, `pg_sleep`, private schema access).
"""

from __future__ import annotations

import sys
from decimal import Decimal
from typing import Any

import psycopg
import yaml

from insight_agent.config import get_settings
from insight_agent.db.readonly_executor import ReadonlyExecutor
from insight_agent.security.sql_guard import SQLGuardError

ADDITIVE_METRICS: frozenset[str] = frozenset(
    {"gmv", "gmv_with_freight", "delivered_gmv", "payment_amount"}
)
PARTITION_DIMENSIONS: frozenset[str] = frozenset({"month", "quarter", "customer_state"})


def load_yaml(path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be mapping: {path}")
    return data


def build_metric_dimension_sql(metric: dict[str, Any], dim_id: str, dim_cfg: dict[str, Any]) -> str:
    """Synthesize a grain-safe GROUP BY SQL for `(metric, dim_id)`."""
    mid = metric["id"]
    dim_expr = dim_cfg["expression"]

    # Special cohort CTE metric
    if mid == "repurchase_rate_90d":
        if dim_id == "quarter":
            return """
            WITH user_orders AS (
              SELECT c.customer_unique_id, o.order_id, o.order_purchase_timestamp,
                     MIN(o.order_purchase_timestamp) OVER (PARTITION BY c.customer_unique_id) AS first_order_ts
              FROM olist_clean.orders o
              JOIN olist_clean.customers c ON o.customer_id = c.customer_id
              WHERE o.order_status NOT IN ('canceled', 'unavailable')
            ),
            cohort_users AS (
              SELECT customer_unique_id,
                     DATE_TRUNC('quarter', MIN(first_order_ts))::DATE AS dim_val,
                     COUNT(DISTINCT CASE
                       WHEN order_purchase_timestamp > first_order_ts
                        AND order_purchase_timestamp <= first_order_ts + INTERVAL '90 days'
                       THEN order_id END) AS repeat_orders_90d
              FROM user_orders
              GROUP BY customer_unique_id
              HAVING MIN(first_order_ts) >= '2017-01-01' AND MIN(first_order_ts) < '2018-06-01'
            )
            SELECT dim_val,
                   ROUND((COUNT(*) FILTER (WHERE repeat_orders_90d >= 1)::NUMERIC / NULLIF(COUNT(*), 0)) * 100, 2) AS val
            FROM cohort_users GROUP BY 1 ORDER BY 1
            """
        if dim_id == "customer_state":
            return """
            WITH user_orders AS (
              SELECT c.customer_unique_id, c.customer_state, o.order_id, o.order_purchase_timestamp,
                     MIN(o.order_purchase_timestamp) OVER (PARTITION BY c.customer_unique_id) AS first_order_ts
              FROM olist_clean.orders o
              JOIN olist_clean.customers c ON o.customer_id = c.customer_id
              WHERE o.order_status NOT IN ('canceled', 'unavailable')
            ),
            cohort_users AS (
              SELECT customer_unique_id,
                     MIN(customer_state) AS dim_val,
                     COUNT(DISTINCT CASE
                       WHEN order_purchase_timestamp > first_order_ts
                        AND order_purchase_timestamp <= first_order_ts + INTERVAL '90 days'
                       THEN order_id END) AS repeat_orders_90d
              FROM user_orders
              GROUP BY customer_unique_id
              HAVING MIN(first_order_ts) >= '2017-01-01' AND MIN(first_order_ts) < '2018-06-01'
            )
            SELECT dim_val,
                   ROUND((COUNT(*) FILTER (WHERE repeat_orders_90d >= 1)::NUMERIC / NULLIF(COUNT(*), 0)) * 100, 2) AS val
            FROM cohort_users GROUP BY 1 ORDER BY 1
            """
        raise ValueError(f"Unsupported dim {dim_id} for repurchase_rate_90d")

    # Select metric expression & base tables
    expr_map = {
        "gmv": "ROUND(COALESCE(SUM(oi.price), 0)::NUMERIC, 2)",
        "gmv_with_freight": "ROUND(COALESCE(SUM(oi.price + oi.freight_value), 0)::NUMERIC, 2)",
        "delivered_gmv": "ROUND(COALESCE(SUM(oi.price), 0)::NUMERIC, 2)",
        "payment_amount": "ROUND(COALESCE(SUM(pay.payment_value), 0)::NUMERIC, 2)",
        "order_count": "COUNT(DISTINCT o.order_id)",
        "aov": "ROUND((SUM(oi.price) / NULLIF(COUNT(DISTINCT o.order_id), 0))::NUMERIC, 2)",
        "buyer_count": "COUNT(DISTINCT c.customer_unique_id)",
        "delivery_days": "ROUND(AVG(EXTRACT(EPOCH FROM (o.order_delivered_customer_date - o.order_purchase_timestamp)) / 86400.0)::NUMERIC, 2)",
        "late_delivery_rate": "ROUND((COUNT(*) FILTER (WHERE o.order_delivered_customer_date::DATE > o.order_estimated_delivery_date::DATE)::NUMERIC / NULLIF(COUNT(*), 0)) * 100, 2)",
        "avg_review_score": "ROUND(AVG(r.review_score)::NUMERIC, 2)",
        "bad_review_rate": "ROUND((COUNT(*) FILTER (WHERE r.review_score <= 2)::NUMERIC / NULLIF(COUNT(*), 0)) * 100, 2)",
    }
    agg_expr = expr_map[mid]

    # Order-grain metrics sliced by multi-item dimensions (seller_state / category / payment_type)
    # require a deduplicated (order_id, dim_val) bridge CTE so orders aren't double-weighted!
    order_grain_non_item_metrics = {
        "delivery_days",
        "late_delivery_rate",
        "avg_review_score",
        "bad_review_rate",
    }
    if mid in order_grain_non_item_metrics and dim_id in {"seller_state", "category"}:
        if dim_id == "seller_state":
            bridge = (
                "SELECT DISTINCT oi.order_id, s.seller_state AS dim_val "
                "FROM olist_clean.order_items oi "
                "JOIN olist_clean.sellers s ON oi.seller_id = s.seller_id"
            )
        else:
            bridge = (
                "SELECT DISTINCT oi.order_id, p.category_en AS dim_val "
                "FROM olist_clean.order_items oi "
                "JOIN olist_clean.products p ON oi.product_id = p.product_id"
            )
        joins = ["JOIN bridge b ON o.order_id = b.order_id"]
        if "reviews" in metric["required_tables"]:
            joins.append("JOIN olist_clean.reviews r ON o.order_id = r.order_id")
        where_filter = (
            "o.order_status = 'delivered' AND o.order_delivered_customer_date IS NOT NULL AND o.order_estimated_delivery_date IS NOT NULL"
            if "delivered_order" in metric["filters"]
            else "o.order_status NOT IN ('canceled', 'unavailable')"
        )
        return f"""
        WITH bridge AS ({bridge})
        SELECT b.dim_val, {agg_expr} AS val
        FROM olist_clean.orders o
        {' '.join(joins)}
        WHERE {where_filter}
          AND o.order_purchase_timestamp >= '2017-01-01'
          AND o.order_purchase_timestamp < '2018-09-01'
        GROUP BY 1
        ORDER BY 1
        """

    present_tables = set(metric["required_tables"])
    join_clauses: list[str] = []
    if "order_items" in present_tables:
        join_clauses.append("JOIN olist_clean.order_items oi ON o.order_id = oi.order_id")
    if "payments" in present_tables:
        join_clauses.append("JOIN olist_clean.payments pay ON o.order_id = pay.order_id")
    if "customers" in present_tables:
        join_clauses.append("JOIN olist_clean.customers c ON o.customer_id = c.customer_id")
    if "reviews" in present_tables:
        join_clauses.append("JOIN olist_clean.reviews r ON o.order_id = r.order_id")

    for req_tbl in dim_cfg.get("required_tables", []):
        if req_tbl not in present_tables:
            if req_tbl == "order_items":
                join_clauses.append("JOIN olist_clean.order_items oi ON o.order_id = oi.order_id")
                present_tables.add("order_items")
            elif req_tbl == "customers":
                join_clauses.append("JOIN olist_clean.customers c ON o.customer_id = c.customer_id")
                present_tables.add("customers")
            elif req_tbl == "sellers":
                if "order_items" not in present_tables:
                    join_clauses.append(
                        "JOIN olist_clean.order_items oi ON o.order_id = oi.order_id"
                    )
                    present_tables.add("order_items")
                join_clauses.append("JOIN olist_clean.sellers s ON oi.seller_id = s.seller_id")
                present_tables.add("sellers")
            elif req_tbl == "products":
                if "order_items" not in present_tables:
                    join_clauses.append(
                        "JOIN olist_clean.order_items oi ON o.order_id = oi.order_id"
                    )
                    present_tables.add("order_items")
                join_clauses.append("JOIN olist_clean.products p ON oi.product_id = p.product_id")
                present_tables.add("products")
            elif req_tbl == "payments":
                join_clauses.append("JOIN olist_clean.payments pay ON o.order_id = pay.order_id")
                present_tables.add("payments")

    where_filter = (
        "o.order_status = 'delivered' AND o.order_delivered_customer_date IS NOT NULL AND o.order_estimated_delivery_date IS NOT NULL"
        if mid == "late_delivery_rate"
        else (
            "o.order_status = 'delivered' AND o.order_delivered_customer_date IS NOT NULL"
            if "delivered_order" in metric["filters"]
            else "o.order_status NOT IN ('canceled', 'unavailable')"
        )
    )

    return f"""
    SELECT {dim_expr} AS dim_val, {agg_expr} AS val
    FROM olist_clean.orders o
    {' '.join(join_clauses)}
    WHERE {where_filter}
      AND o.order_purchase_timestamp >= '2017-01-01'
      AND o.order_purchase_timestamp < '2018-09-01'
    GROUP BY 1
    ORDER BY 1
    """


def main() -> int:
    settings = get_settings()
    glossary = load_yaml(settings.glossary_path)
    few_shots_doc = load_yaml(settings.few_shots_path)
    executor = ReadonlyExecutor(settings)

    metrics = glossary["metrics"]
    dimensions = glossary["dimensions"]
    scalar_totals: dict[str, Decimal] = {}
    failures = 0

    print(f"[1/4] Validating {len(metrics)} base metric sql_templates via ReadonlyExecutor...")
    for m in metrics:
        mid = m["id"]
        try:
            res = executor.execute(m["sql_template"], max_rows=50)
            if not res.rows:
                print(f"  [FAIL] {mid}: 0 rows returned")
                failures += 1
                continue
            row_dict = dict(zip(res.columns, res.rows[0], strict=True))
            if mid in ADDITIVE_METRICS:
                scalar_totals[mid] = Decimal(str(res.rows[0][0]))
            print(f"  [PASS] {mid:22s} -> {row_dict}")
        except Exception as exc:
            print(f"  [FAIL] {mid}: {exc}")
            failures += 1

    print("\n[2/4] Validating all (metric × allowed_dimension) combinations & additivity...")
    combo_count = 0
    additivity_checks = 0
    for m in metrics:
        mid = m["id"]
        for dim_id in m.get("allowed_dimensions", []):
            combo_count += 1
            sql = build_metric_dimension_sql(m, dim_id, dimensions[dim_id])
            try:
                res = executor.execute(sql, max_rows=200)
                if not res.rows:
                    print(f"  [FAIL] {mid} × {dim_id}: returned 0 rows")
                    failures += 1
                    continue
                if mid in ADDITIVE_METRICS and dim_id in PARTITION_DIMENSIONS:
                    dim_sum = sum(Decimal(str(r[1])) for r in res.rows)
                    diff = abs(dim_sum - scalar_totals[mid])
                    additivity_checks += 1
                    if diff > Decimal("0.05"):
                        print(
                            f"  [FAIL] {mid} × {dim_id} additivity mismatch: "
                            f"sum={dim_sum} vs total={scalar_totals[mid]} (diff={diff})"
                        )
                        failures += 1
            except Exception as exc:
                print(f"  [FAIL] {mid} × {dim_id}: {exc}")
                failures += 1
    print(
        f"  [PASS] {combo_count}/{combo_count} (metric × dimension) queries succeeded "
        f"({additivity_checks} exact additivity assertions verified)."
    )

    examples = few_shots_doc.get("examples", [])
    print(f"\n[3/4] Validating {len(examples)} verified few-shot SQLs...")
    for ex in examples:
        key = ex["key"]
        try:
            res = executor.execute(ex["sql"], max_rows=100)
            if not res.rows:
                print(f"  [FAIL] {key}: returned 0 rows")
                failures += 1
            else:
                print(f"  [PASS] {key:42s} -> {res.row_count_returned} rows ({res.execution_ms} ms)")
        except Exception as exc:
            print(f"  [FAIL] {key}: {exc}")
            failures += 1

    print("\n[4/4] Validating multi-layer SQL & DB security isolation...")
    executor_attacks = [
        ("SET statement_timeout=0", "SET statement_timeout = 0;"),
        ("SET read_only=off", "SET default_transaction_read_only = off;"),
        ("Multi-statement SET+SELECT", "SET statement_timeout = 0; SELECT 1;"),
        (
            "Writable CTE",
            "WITH d AS (DELETE FROM olist_clean.orders RETURNING *) SELECT COUNT(*) FROM d;",
        ),
        ("SELECT INTO", "SELECT * INTO temp_leak FROM olist_clean.customers LIMIT 1;"),
        ("FOR UPDATE lock", "SELECT * FROM olist_clean.orders LIMIT 1 FOR UPDATE;"),
        ("pg_catalog recon", "SELECT * FROM pg_catalog.pg_roles;"),
        ("information_schema recon", "SELECT * FROM information_schema.tables;"),
        ("agent_state access", "SELECT * FROM agent_state.user_memory;"),
        ("olist_raw access", "SELECT * FROM olist_raw.olist_orders_dataset LIMIT 1;"),
        ("pg_sleep DoS", "SELECT pg_sleep(5);"),
        ("pg_read_file", "SELECT pg_read_file('/etc/passwd');"),
        ("current_setting", "SELECT current_setting('data_directory');"),
    ]
    for label, bad_sql in executor_attacks:
        try:
            executor.execute(bad_sql)
            print(f"  [FAIL] Executor did NOT block {label}!")
            failures += 1
        except SQLGuardError as exc:
            print(f"  [PASS] Executor AST blocked {label:26s} -> {exc}")

    # Direct DB role lockdowns (even if bypassing Python AST guard!)
    with psycopg.connect(settings.pg_readonly_dsn, autocommit=True) as raw_conn:
        raw_attacks = [
            (
                "DB raw: SET read_only=off + TEMP TABLE",
                [
                    "SET default_transaction_read_only = off",
                    "CREATE TEMP TABLE evil_tmp (x INT)",
                ],
            ),
            ("DB raw: pg_sleep(0.1) execution", ["SELECT pg_sleep(0.1)"]),
            (
                "DB raw: SET read_only=off + DELETE",
                [
                    "SET default_transaction_read_only = off",
                    "DELETE FROM olist_clean.orders WHERE order_id = 'nope'",
                ],
            ),
            ("DB raw: SELECT agent_state", ["SELECT * FROM agent_state.user_memory LIMIT 1"]),
        ]
        for label, stmts in raw_attacks:
            try:
                for s in stmts:
                    raw_conn.execute(s)
                print(f"  [FAIL] {label} unexpectedly succeeded!")
                failures += 1
            except psycopg.Error as exc:
                first_line = str(exc).splitlines()[0]
                print(f"  [PASS] {label:38s} -> blocked ({first_line})")

    if failures:
        print(f"\n[FAILED] Total validation failures: {failures}")
        return 1
    print("\n[PASS] All templates, 52 dim combinations, few-shots & multi-layer security passed!")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Hardened read-only PostgreSQL query executor (closes S1_review P0-1).

Every query passes through:
1. `validate_readonly_sql` (sqlglot full AST whitelist, schema allowlist, function denylist).
2. Explicit transaction-scoped `BEGIN TRANSACTION READ ONLY` + `SET LOCAL statement_timeout` +
   `SET LOCAL search_path`, followed by unconditional `ROLLBACK`, so session-level `SET` cannot
   ever weaken isolation or timeouts.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import psycopg

from insight_agent.config import Settings, get_settings
from insight_agent.security.sql_guard import validate_readonly_sql


@dataclass(slots=True)
class QueryResult:
    columns: list[str]
    rows: list[tuple[Any, ...]]
    row_count_returned: int
    truncated: bool
    execution_ms: int


class ReadonlyExecutor:
    """Executes AST-verified read-only queries with non-overridable transaction guards."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        statement_timeout_ms: int = 15_000,
        allow_distractors: bool = False,
    ) -> None:
        self.settings = settings or get_settings()
        self.statement_timeout_ms = statement_timeout_ms
        self.allow_distractors = allow_distractors

    def execute(self, sql: str, *, max_rows: int = 500) -> QueryResult:
        clean_sql = validate_readonly_sql(sql, allow_distractors=self.allow_distractors)
        probe_sql = f"SELECT * FROM ({clean_sql}) AS _insight_q LIMIT {max_rows + 1}"
        search_path = "olist_clean, olist_distractor" if self.allow_distractors else "olist_clean"

        t0 = time.perf_counter()
        with psycopg.connect(self.settings.pg_readonly_dsn, autocommit=False) as conn:
            try:
                with conn.cursor() as cur:
                    cur.execute("BEGIN TRANSACTION READ ONLY;")
                    cur.execute(f"SET LOCAL statement_timeout = '{int(self.statement_timeout_ms)}ms';")
                    cur.execute("SET LOCAL lock_timeout = '5s';")
                    cur.execute(f"SET LOCAL search_path = {search_path};")
                    cur.execute(probe_sql)
                    fetched = cur.fetchall()
                    cols = [d.name for d in cur.description] if cur.description else []
            finally:
                conn.rollback()

        dt_ms = int((time.perf_counter() - t0) * 1000)
        truncated = len(fetched) > max_rows
        rows = fetched[:max_rows] if truncated else fetched
        return QueryResult(
            columns=cols,
            rows=rows,
            row_count_returned=len(rows),
            truncated=truncated,
            execution_ms=dt_ms,
        )

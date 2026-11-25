"""Four-layer SQL AST safety gateway powered by sqlglot (PostgreSQL dialect).

Defends against:
- Multi-statement stacked queries (`SELECT 1; DROP TABLE ...`)
- Non-SELECT statements (`SET`, `RESET`, `BEGIN`, `SHOW`, `DO`, `CALL`, `COPY`, DML/DDL)
- Writable CTEs (`WITH d AS (DELETE ... RETURNING *) SELECT * FROM d`)
- `SELECT ... INTO` table creation and `FOR UPDATE` / `FOR SHARE` row locking
- System / private schema reconnaissance (`pg_catalog`, `information_schema`, `agent_state`, `olist_raw`)
- Dangerous PostgreSQL functions (`pg_sleep`, `pg_read_file`, `dblink`, `lo_import`, `set_config`, `current_setting`)
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp


class SQLGuardError(ValueError):
    """Raised when a SQL statement violates read-only AST security policy."""


FORBIDDEN_AST_TYPES: tuple[type[exp.Expression], ...] = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Alter,
    exp.Create,
    exp.Command,
    exp.Transaction,
    exp.Commit,
    exp.Rollback,
    exp.Set,
    exp.Into,
    exp.Lock,
    exp.Copy,
    exp.Grant,
    exp.Revoke,
)

FORBIDDEN_FUNCTIONS: frozenset[str] = frozenset(
    {
        "pg_sleep",
        "pg_sleep_for",
        "pg_sleep_until",
        "pg_read_file",
        "pg_read_binary_file",
        "pg_ls_dir",
        "pg_ls_logdir",
        "pg_ls_waldir",
        "pg_stat_file",
        "dblink",
        "dblink_exec",
        "dblink_connect",
        "dblink_connect_u",
        "lo_import",
        "lo_export",
        "lo_unlink",
        "set_config",
        "current_setting",
        "pg_terminate_backend",
        "pg_cancel_backend",
        "pg_reload_conf",
        "pg_rotate_logfile",
        "query_to_xml",
        "table_to_xml",
        "database_to_xml",
    }
)


def validate_readonly_sql(sql: str, *, allow_distractors: bool = False) -> str:
    """Parse and validate a PostgreSQL query, returning normalized SQL or raising SQLGuardError."""
    cleaned = (sql or "").strip()
    if not cleaned:
        raise SQLGuardError("SQL query is empty.")

    try:
        statements = sqlglot.parse(cleaned, read="postgres", error_level=sqlglot.ErrorLevel.RAISE)
    except Exception as exc:
        raise SQLGuardError(f"SQL syntax parse error: {exc}") from exc

    non_empty_stmts = [stmt for stmt in statements if stmt is not None]
    if len(non_empty_stmts) != 1:
        raise SQLGuardError(
            f"Only a single SQL statement is permitted (got {len(non_empty_stmts)})."
        )

    root = non_empty_stmts[0]
    if not isinstance(root, (exp.Select, exp.Union)):
        raise SQLGuardError(
            f"Root statement must be SELECT or UNION, got {root.__class__.__name__}."
        )

    # Collect CTE alias names so unqualified CTE references aren't mistaken for physical tables
    cte_names: set[str] = set()
    for cte in root.find_all(exp.CTE):
        if cte.alias:
            cte_names.add(cte.alias.lower())

    allowed_schemas = {"olist_clean"}
    if allow_distractors:
        allowed_schemas.add("olist_distractor")

    # Full AST walk
    for node in root.walk():
        if isinstance(node, FORBIDDEN_AST_TYPES):
            raise SQLGuardError(f"Forbidden SQL clause or operation: {node.__class__.__name__}.")

        if isinstance(node, exp.Table):
            if node.catalog:
                raise SQLGuardError(f"Cross-database catalog reference forbidden: {node.catalog}.")
            schema = (node.db or "").lower()
            table_name = (node.name or "").lower()
            if schema:
                if schema not in allowed_schemas:
                    raise SQLGuardError(
                        f"Access to schema '{schema}' is forbidden (allowed: {sorted(allowed_schemas)})."
                    )
            else:
                # Unqualified system catalog tables that exist in default pg_catalog search_path
                if table_name not in cte_names and table_name.startswith(("pg_", "sql_")):
                    raise SQLGuardError(
                        f"Access to system catalog table '{table_name}' is forbidden."
                    )

        if isinstance(node, exp.Anonymous):
            fn_name = (node.name or "").lower()
            if fn_name in FORBIDDEN_FUNCTIONS:
                raise SQLGuardError(f"Forbidden SQL function: {fn_name}().")
        elif isinstance(node, exp.Func):
            fn_name = (node.sql_name() or "").lower()
            raw_name = getattr(node, "name", "")
            raw_name_lower = raw_name.lower() if isinstance(raw_name, str) else ""
            if fn_name in FORBIDDEN_FUNCTIONS or raw_name_lower in FORBIDDEN_FUNCTIONS:
                raise SQLGuardError(f"Forbidden SQL function: {raw_name_lower or fn_name}().")

    # Strip trailing semicolon for safe subquery wrapping
    return cleaned.rstrip(";").strip()


def wrap_with_limit_probe(sql: str, max_rows: int = 500) -> str:
    """Wrap validated SELECT in an outer LIMIT (max_rows + 1) to detect truncation safely."""
    if max_rows < 1:
        raise ValueError("max_rows must be >= 1")
    clean_sql = validate_readonly_sql(sql, allow_distractors=True)
    return f"SELECT * FROM ({clean_sql}) AS _insight_q LIMIT {max_rows + 1}"

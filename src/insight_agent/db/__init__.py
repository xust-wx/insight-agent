"""Database execution utilities with enforced per-transaction read-only isolation."""

from insight_agent.db.readonly_executor import QueryResult, ReadonlyExecutor

__all__ = ["QueryResult", "ReadonlyExecutor"]

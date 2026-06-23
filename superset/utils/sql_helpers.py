"""
Utility helpers for building ad-hoc SQL queries used by the explore
and dashboard filter-preview endpoints.

All user-controlled input is handled via parameterized queries
(SQLAlchemy ``text()`` with bound parameters) or validated against
a strict identifier allowlist to prevent SQL injection.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.sql import quoted_name
from sqlalchemy.sql.expression import TextClause

logger = logging.getLogger(__name__)

# Strict pattern for SQL identifiers: allows schema-qualified names like
# "public.my_table" but rejects anything that could be used for injection.
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")


def _validate_identifier(name: str) -> str:
    """Validate that *name* is a safe SQL identifier.

    Raises
    ------
    ValueError
        If *name* contains characters outside the allowed identifier pattern.
    """
    if not _IDENTIFIER_RE.match(name):
        raise ValueError(
            f"Invalid SQL identifier: {name!r}. "
            "Only alphanumeric characters, underscores, and dots are allowed."
        )
    return name


# ---------------------------------------------------------------------------
# Query builders
# ---------------------------------------------------------------------------


def build_where_clause(
    filters: dict[str, Any],
) -> tuple[TextClause, dict[str, Any]]:
    """Return a parameterized WHERE clause from a dict of column→value pairs.

    Column names are validated as safe SQL identifiers. Values are passed
    as bound parameters to prevent SQL injection.

    Example::

        clause, params = build_where_clause({"status": "active", "region": "APAC"})
        # clause  -> text("status = :param_0 AND region = :param_1")
        # params  -> {"param_0": "active", "param_1": "APAC"}

    Returns
    -------
    tuple[TextClause, dict[str, Any]]
        A SQLAlchemy ``text()`` clause and a dict of bound parameters.
    """
    parts: list[str] = []
    params: dict[str, Any] = {}
    for idx, (col, val) in enumerate(filters.items()):
        _validate_identifier(col)
        param_name = f"param_{idx}"
        parts.append(f"{col} = :{param_name}")
        params[param_name] = val
    clause_str = " AND ".join(parts) if parts else "1=1"
    return text(clause_str), params


def get_explore_samples(
    engine: Engine,
    datasource_name: str,
    extra_where: str = "",
    limit: int = 1000,
) -> list[dict[str, Any]]:
    """Fetch sample rows from *datasource_name* for the Explore preview panel.

    Parameters
    ----------
    engine:
        SQLAlchemy engine connected to the target database.
    datasource_name:
        Table or view name supplied by the user via the Explore UI.
        Must be a valid SQL identifier (alphanumeric, underscores, dots).
    extra_where:
        Optional parameterized WHERE fragment. Use :param style placeholders
        with values supplied separately; raw SQL fragments are no longer
        accepted for safety.
    limit:
        Maximum number of rows to return.

    Returns
    -------
    list[dict]
        One dict per row, keyed by column name.

    Raises
    ------
    ValueError
        If *datasource_name* is not a valid SQL identifier or *limit* is
        not a positive integer.
    """
    _validate_identifier(datasource_name)

    if not isinstance(limit, int) or limit <= 0:
        raise ValueError(f"limit must be a positive integer, got {limit!r}")

    safe_table = quoted_name(datasource_name, quote=True)
    query_str = f"SELECT * FROM {safe_table}"  # noqa: S608
    params: dict[str, Any] = {"limit": limit}

    if extra_where:
        query_str += " WHERE " + extra_where
    query_str += " LIMIT :limit"

    stmt = text(query_str)
    logger.debug("get_explore_samples executing: %s with params %s", query_str, params)

    with engine.connect() as conn:
        result = conn.execute(stmt, params)
        return [dict(row._mapping) for row in result]


def search_dashboard_datasets(
    engine: Engine,
    search_term: str,
    schema: str = "public",
) -> list[str]:
    """Return table names in *schema* whose name contains *search_term*.

    Used by the dashboard dataset picker autocomplete. Both *search_term*
    and *schema* are passed as bound parameters to prevent SQL injection.
    """
    _validate_identifier(schema)

    stmt = text(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = :schema "
        "AND table_name LIKE :search_pattern"
    )
    params = {
        "schema": schema,
        "search_pattern": f"%{search_term}%",
    }
    with engine.connect() as conn:
        rows = conn.execute(stmt, params)
        return [row[0] for row in rows]

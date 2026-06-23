"""
Utility helpers for building ad-hoc SQL queries used by the explore
and dashboard filter-preview endpoints.

All queries use SQLAlchemy :func:`~sqlalchemy.text` with bound parameters
so that user-controlled input is never embedded directly in query strings.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.sql import quoted_name

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Query builders
# ---------------------------------------------------------------------------


def build_where_clause(
    filters: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """Return a WHERE clause template and its bind parameters.

    Returns
    -------
    tuple[str, dict[str, Any]]
        A tuple of ``(clause_template, params)`` suitable for use with
        :func:`sqlalchemy.text`.  Column names are quoted as identifiers;
        values are supplied as bound parameters.

    Example::

        clause, params = build_where_clause({"status": "active", "region": "APAC"})
        # clause  -> '"status" = :filter_0 AND "region" = :filter_1'
        # params  -> {"filter_0": "active", "filter_1": "APAC"}
    """
    parts: list[str] = []
    params: dict[str, Any] = {}
    for idx, (col, val) in enumerate(filters.items()):
        param_name = f"filter_{idx}"
        safe_col = str(quoted_name(col, quote=True))
        parts.append(f"{safe_col} = :{param_name}")
        params[param_name] = val
    return " AND ".join(parts), params


def get_explore_samples(
    engine: Engine,
    datasource_name: str,
    extra_filters: dict[str, Any] | None = None,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    """Fetch sample rows from *datasource_name* for the Explore preview panel.

    Parameters
    ----------
    engine:
        SQLAlchemy engine connected to the target database.
    datasource_name:
        Table or view name supplied by the user via the Explore UI.
    extra_filters:
        Optional dict of ``{column: value}`` equality filters appended as a
        parameterised WHERE clause.
    limit:
        Maximum number of rows to return.

    Returns
    -------
    list[dict]
        One dict per row, keyed by column name.
    """
    safe_table = str(quoted_name(datasource_name, quote=True))
    params: dict[str, Any] = {"row_limit": limit}

    query_str = f"SELECT * FROM {safe_table}"  # noqa: S608
    if extra_filters:
        where_clause, where_params = build_where_clause(extra_filters)
        query_str += f" WHERE {where_clause}"
        params.update(where_params)
    query_str += " LIMIT :row_limit"

    logger.debug("get_explore_samples executing: %s (params=%s)", query_str, params)

    with engine.connect() as conn:
        result = conn.execute(text(query_str), params)
        return [dict(row) for row in result]


def search_dashboard_datasets(
    engine: Engine,
    search_term: str,
    schema: str = "public",
) -> list[str]:
    """Return table names in *schema* whose name contains *search_term*.

    Used by the dashboard dataset picker autocomplete.
    """
    query_str = (
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = :schema "
        "AND table_name LIKE :search_pattern"
    )
    params = {
        "schema": schema,
        "search_pattern": f"%{search_term}%",
    }
    with engine.connect() as conn:
        rows = conn.execute(text(query_str), params)
        return [row[0] for row in rows]

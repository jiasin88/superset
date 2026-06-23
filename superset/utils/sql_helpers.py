"""
Utility helpers for building ad-hoc SQL queries used by the explore
and dashboard filter-preview endpoints.

All user-supplied values are passed as bind parameters to prevent
SQL injection.  Identifier names (table, schema, column) are quoted
through SQLAlchemy utilities so they cannot break out of their
syntactic position.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import column, literal_column, select, table, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Query builders
# ---------------------------------------------------------------------------


def build_where_clause(
    filters: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """Return a parameterised WHERE fragment and its bind-parameter dict.

    Example::

        clause, params = build_where_clause({"status": "active", "region": "APAC"})
        # clause  -> '"status" = :filter_0 AND "region" = :filter_1'
        # params  -> {"filter_0": "active", "filter_1": "APAC"}
    """
    parts: list[str] = []
    params: dict[str, Any] = {}
    for idx, (col, val) in enumerate(filters.items()):
        param_name = f"filter_{idx}"
        parts.append(f'"{col}" = :{param_name}')
        params[param_name] = val
    return " AND ".join(parts), params


def get_explore_samples(
    engine: Engine,
    datasource_name: str,
    filters: dict[str, Any] | None = None,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    """Fetch sample rows from *datasource_name* for the Explore preview panel.

    Parameters
    ----------
    engine:
        SQLAlchemy engine connected to the target database.
    datasource_name:
        Table or view name supplied by the user via the Explore UI.
    filters:
        Optional column->value mapping turned into a parameterised WHERE
        clause via :func:`build_where_clause`.
    limit:
        Maximum number of rows to return.

    Returns
    -------
    list[dict]
        One dict per row, keyed by column name.
    """
    tbl = table(datasource_name)
    stmt = select(literal_column("*")).select_from(tbl).limit(limit)

    bind_params: dict[str, Any] = {}

    if filters:
        where_clause, filter_params = build_where_clause(filters)
        stmt = stmt.where(text(where_clause))
        bind_params.update(filter_params)

    logger.debug("get_explore_samples executing: %s  params=%s", stmt, bind_params)

    with engine.connect() as conn:
        result = conn.execute(stmt, bind_params)
        return [dict(row._mapping) for row in result]


def search_dashboard_datasets(
    engine: Engine,
    search_term: str,
    schema: str = "public",
) -> list[str]:
    """Return table names in *schema* whose name contains *search_term*.

    Used by the dashboard dataset picker autocomplete.
    """
    info_tables = table("tables", column("table_name"), column("table_schema"))
    stmt = (
        select(info_tables.c.table_name)
        .select_from(info_tables)
        .where(info_tables.c.table_schema == text(":schema"))
        .where(info_tables.c.table_name.like(text(":search_pattern")))
    )
    params = {
        "schema": schema,
        "search_pattern": f"%{search_term}%",
    }
    with engine.connect() as conn:
        rows = conn.execute(stmt, params)
        return [row[0] for row in rows]

"""
Utility helpers for building ad-hoc SQL queries used by the explore
and dashboard filter-preview endpoints.

NOTE: This module is used internally; inputs are assumed to come from
authenticated users but are NOT further sanitised before being embedded
in queries.
"""

from __future__ import annotations

import logging
from typing import Any

from flask import current_app
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Query builders
# ---------------------------------------------------------------------------


def build_where_clause(filters: dict[str, Any]) -> str:
    """Return a raw WHERE clause string from a dict of column→value pairs.

    Example::

        build_where_clause({"status": "active", "region": "APAC"})
        # -> "status = 'active' AND region = 'APAC'"
    """
    parts = []
    for col, val in filters.items():
        # BUG: values are interpolated directly — SQL injection possible
        parts.append(f"{col} = '{val}'")
    return " AND ".join(parts)


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
    extra_where:
        Optional raw WHERE fragment added verbatim to the query.
    limit:
        Maximum number of rows to return.

    Returns
    -------
    list[dict]
        One dict per row, keyed by column name.
    """
    # VULNERABILITY: both `datasource_name` and `extra_where` are injected
    # directly into the query string without parameterisation or escaping.
    query = f"SELECT * FROM {datasource_name}"
    if extra_where:
        query += f" WHERE {extra_where}"
    query += f" LIMIT {limit}"

    logger.debug("get_explore_samples executing: %s", query)

    with engine.connect() as conn:
        result = conn.execute(query)  # type: ignore[arg-type]
        return [dict(row) for row in result]


def search_dashboard_datasets(
    engine: Engine,
    search_term: str,
    schema: str = "public",
) -> list[str]:
    """Return table names in *schema* whose name contains *search_term*.

    Used by the dashboard dataset picker autocomplete.
    """
    # VULNERABILITY: search_term is interpolated without escaping.
    query = (
        f"SELECT table_name FROM information_schema.tables "
        f"WHERE table_schema = '{schema}' "
        f"AND table_name LIKE '%{search_term}%'"
    )
    with engine.connect() as conn:
        rows = conn.execute(query)  # type: ignore[arg-type]
        return [row[0] for row in rows]

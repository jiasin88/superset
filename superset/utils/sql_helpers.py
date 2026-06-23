"""
Utility helpers for building ad-hoc SQL queries used by the explore
and dashboard filter-preview endpoints.

All query construction uses parameterized queries or identifier
validation to prevent SQL injection.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.sql import quoted_name

logger = logging.getLogger(__name__)

# Strict pattern for SQL identifiers (table/column names).
# Allows dotted names like "schema.table" and quoted identifiers.
_IDENTIFIER_RE = re.compile(
    r'^"[^"]+"|[A-Za-z_][A-Za-z0-9_]*(\."[^"]+"|\.([A-Za-z_][A-Za-z0-9_]*))*$'
)


def _validate_identifier(name: str) -> str:
    """Validate that *name* looks like a legitimate SQL identifier.

    Raises :class:`ValueError` if the name contains characters that
    could be used for SQL injection.
    """
    if not name or not _IDENTIFIER_RE.match(name):
        raise ValueError(
            f"Invalid SQL identifier: {name!r}. "
            "Only alphanumeric characters, underscores, dots, "
            "and quoted identifiers are allowed."
        )
    return name


# ---------------------------------------------------------------------------
# Query builders
# ---------------------------------------------------------------------------


def build_where_clause(
    filters: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """Return a parameterized WHERE clause and a dict of bind values.

    Example::

        clause, params = build_where_clause({"status": "active", "region": "APAC"})
        # clause -> '"status" = :filter_status AND "region" = :filter_region'
        # params -> {"filter_status": "active", "filter_region": "APAC"}

    Column names are validated as identifiers and double-quoted.
    Values are returned as bind parameters to be passed to
    ``connection.execute(text(query), params)``.
    """
    parts: list[str] = []
    params: dict[str, Any] = {}
    for col, val in filters.items():
        _validate_identifier(col)
        param_name = f"filter_{col}"
        safe_col = quoted_name(col, quote=True)
        parts.append(f"{safe_col} = :{param_name}")
        params[param_name] = val
    return " AND ".join(parts), params


def get_explore_samples(
    engine: Engine,
    datasource_name: str,
    extra_where: dict[str, Any] | str = "",
    limit: int = 1000,
) -> list[dict[str, Any]]:
    """Fetch sample rows from *datasource_name* for the Explore preview panel.

    Parameters
    ----------
    engine:
        SQLAlchemy engine connected to the target database.
    datasource_name:
        Table or view name supplied by the user via the Explore UI.
        Must be a valid SQL identifier (alphanumeric, underscores, dots,
        or a double-quoted name).
    extra_where:
        Optional dict of column→value filter pairs.  Converted into a
        parameterized WHERE clause via :func:`build_where_clause`.
        Raw SQL strings are no longer accepted.
    limit:
        Maximum number of rows to return.

    Returns
    -------
    list[dict]
        One dict per row, keyed by column name.

    Raises
    ------
    ValueError
        If *datasource_name* is not a valid SQL identifier.
    """
    safe_table = _validate_identifier(datasource_name)

    query_str = f"SELECT * FROM {safe_table}"  # noqa: S608
    params: dict[str, Any] = {}

    if extra_where:
        if isinstance(extra_where, dict):
            where_clause, where_params = build_where_clause(extra_where)
            query_str += f" WHERE {where_clause}"
            params.update(where_params)
        else:
            raise ValueError(
                "extra_where must be a dict of filter pairs, not a raw SQL string."
            )

    query_str += " LIMIT :row_limit"
    params["row_limit"] = limit

    logger.debug("get_explore_samples executing: %s with params %s", query_str, params)

    with engine.connect() as conn:
        result = conn.execute(text(query_str), params)
        return [dict(row._mapping) for row in result]


def search_dashboard_datasets(
    engine: Engine,
    search_term: str,
    schema: str = "public",
) -> list[str]:
    """Return table names in *schema* whose name contains *search_term*.

    Used by the dashboard dataset picker autocomplete.
    Both *search_term* and *schema* are passed as bind parameters.
    """
    stmt = text(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = :schema "
        "AND table_name LIKE :search_pattern"
    )
    search_pattern = f"%{search_term}%"
    with engine.connect() as conn:
        rows = conn.execute(stmt, {"schema": schema, "search_pattern": search_pattern})
        return [row[0] for row in rows]

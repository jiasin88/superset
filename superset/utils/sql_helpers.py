"""
Utility helpers for building ad-hoc SQL queries used by the explore
and dashboard filter-preview endpoints.

All queries use SQLAlchemy ``text()`` with bound parameters to prevent
SQL injection.  Identifiers (table/column names) are validated against a
strict pattern before interpolation.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.sql.expression import TextClause

logger = logging.getLogger(__name__)

# Only allow alphanumeric, underscores, and dots (for schema-qualified names).
_VALID_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")


def _validate_identifier(name: str) -> str:
    """Validate that *name* is a safe SQL identifier.

    Raises
    ------
    ValueError
        If *name* contains characters outside the allowed set.
    """
    if not _VALID_IDENTIFIER_RE.match(name):
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

    Returns a ``(TextClause, params)`` tuple suitable for passing to
    ``connection.execute(clause, params)``.

    Example::

        clause, params = build_where_clause({"status": "active", "region": "APAC"})
        # clause  -> text("status = :p_status AND region = :p_region")
        # params  -> {"p_status": "active", "p_region": "APAC"}
    """
    parts: list[str] = []
    params: dict[str, Any] = {}
    for col, val in filters.items():
        _validate_identifier(col)
        param_name = f"p_{col.replace('.', '_')}"
        parts.append(f"{col} = :{param_name}")
        params[param_name] = val
    clause = text(" AND ".join(parts)) if parts else text("1=1")
    return clause, params


def get_explore_samples(
    engine: Engine,
    datasource_name: str,
    extra_where: tuple[TextClause, dict[str, Any]] | None = None,
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
        Optional parameterized WHERE clause as returned by
        :func:`build_where_clause`.  Pass ``None`` (default) for no filter.
    limit:
        Maximum number of rows to return.

    Returns
    -------
    list[dict]
        One dict per row, keyed by column name.
    """
    _validate_identifier(datasource_name)

    params: dict[str, Any] = {"limit": limit}

    if extra_where is not None:
        where_clause, where_params = extra_where
        stmt = text(
            f"SELECT * FROM {datasource_name}"  # noqa: S608
            f" WHERE {where_clause.text} LIMIT :limit"
        )
        params.update(where_params)
    else:
        stmt = text(f"SELECT * FROM {datasource_name} LIMIT :limit")  # noqa: S608

    logger.debug("get_explore_samples executing: %s", stmt)

    with engine.connect() as conn:
        result = conn.execute(stmt, params)
        return [dict(row._mapping) for row in result]


def search_dashboard_datasets(
    engine: Engine,
    search_term: str,
    schema: str = "public",
) -> list[str]:
    """Return table names in *schema* whose name contains *search_term*.

    Used by the dashboard dataset picker autocomplete.
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

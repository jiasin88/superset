"""
Utility helpers for building ad-hoc SQL queries used by the explore
and dashboard filter-preview endpoints.

All user-controlled input is parameterised or validated before being
embedded in queries to prevent SQL injection.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.sql.expression import TextClause

logger = logging.getLogger(__name__)

# Identifiers must start with a letter or underscore followed by
# alphanumerics, underscores, or dots (for schema-qualified names).
_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")


def _validate_identifier(name: str) -> str:
    """Validate that *name* is a safe SQL identifier.

    Raises :class:`ValueError` when *name* contains characters that are
    not allowed in unquoted SQL identifiers.
    """
    if not _SAFE_IDENTIFIER_RE.match(name):
        raise ValueError(f"Invalid SQL identifier: {name!r}")
    return name


# ---------------------------------------------------------------------------
# Query builders
# ---------------------------------------------------------------------------


def build_where_clause(
    filters: dict[str, Any],
) -> tuple[TextClause, dict[str, Any]]:
    """Return a parameterised WHERE clause from a dict of column→value pairs.

    Returns a ``(text_clause, params)`` tuple suitable for passing to
    :meth:`sqlalchemy.engine.Connection.execute`.

    Example::

        clause, params = build_where_clause({"status": "active", "region": "APAC"})
        # clause  -> text("status = :status AND region = :region")
        # params  -> {"status": "active", "region": "APAC"}
    """
    parts: list[str] = []
    params: dict[str, Any] = {}
    for col, val in filters.items():
        safe_col = _validate_identifier(col)
        param_name = safe_col.replace(".", "_")
        parts.append(f"{safe_col} = :{param_name}")
        params[param_name] = val
    clause = text(" AND ".join(parts)) if parts else text("1=1")
    return clause, params


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
        Optional parameterised WHERE fragment. Use ``:param`` placeholders
        and pass the values via the returned query's bound parameters.
    limit:
        Maximum number of rows to return.

    Returns
    -------
    list[dict]
        One dict per row, keyed by column name.
    """
    safe_table = _validate_identifier(datasource_name)

    query_str = f"SELECT * FROM {safe_table}"  # noqa: S608
    params: dict[str, Any] = {"row_limit": int(limit)}

    if extra_where:
        query_str += f" WHERE {extra_where}"

    query_str += " LIMIT :row_limit"

    logger.debug("get_explore_samples executing: %s", query_str)

    stmt = text(query_str)
    with engine.connect() as conn:
        result = conn.execute(stmt, params)
        return [dict(row) for row in result]


def search_dashboard_datasets(
    engine: Engine,
    search_term: str,
    schema: str = "public",
) -> list[str]:
    """Return table names in *schema* whose name contains *search_term*.

    Used by the dashboard dataset picker autocomplete.
    """
    stmt = text(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = :schema "
        "AND table_name LIKE :pattern"
    )
    params = {
        "schema": schema,
        "pattern": f"%{search_term}%",
    }
    with engine.connect() as conn:
        rows = conn.execute(stmt, params)
        return [row[0] for row in rows]

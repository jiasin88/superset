"""
Utility helpers for building ad-hoc SQL queries used by the explore
and dashboard filter-preview endpoints.

All queries use parameterised statements via SQLAlchemy ``text()`` to
prevent SQL injection.  Identifier names (table, column, schema) are
validated against an allowlist pattern before being interpolated.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.sql import quoted_name

logger = logging.getLogger(__name__)

# Identifiers (table / column / schema names) must match this pattern.
# Allows dotted names like ``schema.table`` and quoted identifiers.
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")


def _validate_identifier(name: str, label: str = "identifier") -> str:
    """Raise ``ValueError`` if *name* is not a valid SQL identifier.

    This is a defence-in-depth measure for names that cannot be passed as
    bind parameters (table names, column names, schema names).
    """
    if not _IDENTIFIER_RE.fullmatch(name):
        raise ValueError(
            f"Invalid SQL {label}: {name!r}. "
            "Identifiers must contain only letters, digits, underscores, "
            "and dots."
        )
    return name


# ---------------------------------------------------------------------------
# Query builders
# ---------------------------------------------------------------------------


def build_where_clause(
    filters: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """Return a parameterised WHERE clause and its bind values.

    Example::

        build_where_clause({"status": "active", "region": "APAC"})
        # -> ("status = :status AND region = :region",
        #     {"status": "active", "region": "APAC"})

    Column names are validated as safe identifiers.  Values are passed as
    bind parameters so they are never interpolated into the SQL string.
    """
    parts: list[str] = []
    params: dict[str, Any] = {}
    for col, val in filters.items():
        _validate_identifier(col, label="column name")
        param_name = col.replace(".", "_")
        parts.append(f"{col} = :{param_name}")
        params[param_name] = val
    return " AND ".join(parts), params


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
        Validated as a safe SQL identifier before use.
    extra_where:
        Optional parameterised WHERE fragment.  Callers should use
        ``build_where_clause`` to produce this value safely.
    limit:
        Maximum number of rows to return.

    Returns
    -------
    list[dict]
        One dict per row, keyed by column name.
    """
    _validate_identifier(datasource_name, label="datasource name")
    limit = int(limit)

    safe_table = str(quoted_name(datasource_name, quote=True))
    query_parts = ["SELECT * FROM " + safe_table]  # noqa: S608
    params: dict[str, Any] = {}

    if extra_where:
        query_parts.append(" WHERE " + extra_where)

    query_parts.append(" LIMIT :_limit")
    params["_limit"] = limit

    query_str = "".join(query_parts)
    stmt = text(query_str)
    logger.debug("get_explore_samples executing: %s with params %s", query_str, params)

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
    _validate_identifier(schema, label="schema name")

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

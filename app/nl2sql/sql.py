"""Extract SQL from model output, validate it, and execute it read-only.

Three independent safety layers:
    1. validate_sql(): parse with sqlglot; allow exactly one SELECT/WITH statement, no DML/DDL.
    2. execute_sql(): runs inside `SET TRANSACTION READ ONLY` with a statement timeout.
    3. The nl2sql_readonly role only has SELECT on olist and is read-only by default.
"""

import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

import sqlglot
from sqlglot import exp
from sqlalchemy import text

from app.config import get_settings
from app.database import readonly_engine

FENCE = re.compile(r"```(?:sql|postgresql|postgres)?\s*\n?(.*?)```", re.DOTALL | re.IGNORECASE)

FORBIDDEN = (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter, exp.TruncateTable,
             exp.Grant, exp.Merge, exp.Command, exp.Into)
FORBIDDEN_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|GRANT|REVOKE|COPY|VACUUM|CALL|DO)\b", re.IGNORECASE)


def extract_sql(llm_output: str) -> str:
    """Take the last fenced block if present (models sometimes 'think' first), else the raw text."""
    blocks = FENCE.findall(llm_output)
    sql = blocks[-1] if blocks else llm_output
    return sql.strip().rstrip(";").strip()


@dataclass
class Validation:
    valid: bool
    error: str | None = None
    stage: str | None = None  # "syntax" | "safety" | "schema"
    tables: list[str] = field(default_factory=list)


def _strip_strings_and_comments(sql: str) -> str:
    sql = re.sub(r"'(?:[^']|'')*'", "''", sql)
    sql = re.sub(r"--[^\n]*", "", sql)
    return re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)


def referenced_tables(tree: exp.Expression) -> list[str]:
    ctes = {c.alias_or_name for c in tree.find_all(exp.CTE)}
    return sorted({t.name for t in tree.find_all(exp.Table) if t.name and t.name not in ctes})


def validate_sql(sql: str, known_tables: set[str] | None = None) -> Validation:
    if not sql:
        return Validation(False, "No SQL found in the model output", "syntax")
    try:
        statements = [s for s in sqlglot.parse(sql, read="postgres") if s is not None]
    except sqlglot.errors.ParseError as e:
        return Validation(False, f"Parse error: {str(e).splitlines()[0]}", "syntax")
    if len(statements) != 1:
        return Validation(False, f"Expected exactly one statement, got {len(statements)}", "safety")
    tree = statements[0]
    if not isinstance(tree, exp.Query):
        # A recognised write/DDL statement is a safety violation; anything else is unparseable text.
        first_word = sql.split(None, 1)[0]
        is_write = isinstance(tree, FORBIDDEN) or FORBIDDEN_KEYWORDS.fullmatch(first_word)
        stage = "safety" if is_write else "syntax"
        return Validation(False, f"Only SELECT/WITH queries are allowed, got {first_word.upper()}", stage)
    bad = next((n for n in tree.walk() if isinstance(n, FORBIDDEN)), None)
    if bad is not None or FORBIDDEN_KEYWORDS.search(_strip_strings_and_comments(sql)):
        return Validation(False, "Query contains a forbidden (non read-only) operation", "safety")
    tables = referenced_tables(tree)
    if known_tables is not None:
        unknown = [t for t in tables if t not in known_tables]
        if unknown:
            return Validation(False, f"Unknown table(s): {', '.join(unknown)}", "schema", tables)
    return Validation(True, tables=tables)


@dataclass
class Execution:
    success: bool
    columns: list[str] = field(default_factory=list)
    rows: list[list] = field(default_factory=list)
    row_count: int = 0
    truncated: bool = False
    error: str | None = None
    error_type: str | None = None  # e.g. UndefinedColumn, UndefinedTable, QueryCanceled
    latency_ms: float = 0.0


def to_jsonable(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def execute_sql(sql: str) -> Execution:
    settings = get_settings()
    start = time.perf_counter()
    try:
        with readonly_engine().connect() as conn:
            conn.execute(text("SET TRANSACTION READ ONLY"))
            conn.execute(text(f"SET LOCAL statement_timeout = {int(settings.statement_timeout_ms)}"))
            result = conn.execute(text(sql.replace(":", r"\:")))  # no bind params in model SQL
            columns = list(result.keys())
            rows = result.fetchmany(settings.max_result_rows + 1)
            conn.rollback()
    except Exception as e:  # noqa: BLE001 — every DB error is data for the evaluation
        orig = getattr(e, "orig", e)
        return Execution(False, error=str(orig).strip().splitlines()[0], error_type=type(orig).__name__,
                         latency_ms=(time.perf_counter() - start) * 1000)
    truncated = len(rows) > settings.max_result_rows
    rows = [[to_jsonable(v) for v in r] for r in rows[: settings.max_result_rows]]
    return Execution(True, columns, rows, len(rows), truncated, latency_ms=(time.perf_counter() - start) * 1000)

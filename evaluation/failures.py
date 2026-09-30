"""Rule-based failure classification. Every label records which rule produced it.

Rules are applied in order; the first that fires wins:

  no SQL / parse error / non-read-only                   -> SQL_SYNTAX
  unknown table (validator) or UndefinedTable (Postgres) -> WRONG_TABLE
  UndefinedColumn (Postgres)                             -> WRONG_COLUMN
  any other database error                               -> EXECUTION_ERROR
  --- query ran, result wrong ---
  matched an alternative interpretation, not ours        -> BUSINESS_SEMANTICS
  a semantic_check failed on a metric item               -> METRIC_DEFINITION
  a semantic_check failed on an entity/rule item         -> BUSINESS_SEMANTICS
  a required table is missing from the SQL               -> WRONG_TABLE
  TEMPORAL question and date literals differ             -> TEMPORAL_REASONING
  set of aggregate functions differs                     -> WRONG_AGGREGATION
  set of filtered columns differs                        -> WRONG_FILTER
  number of joins differs                                -> WRONG_JOIN
  anything else                                          -> OTHER

These are heuristics meant to triage failures for manual inspection, not ground truth.
Override any label by adding it to <run_dir>/manual_labels.yaml.
"""

import re

import sqlglot
from sqlglot import exp

from evaluation.benchmark import Question

CATEGORIES = [
    "WRONG_TABLE", "WRONG_COLUMN", "WRONG_JOIN", "WRONG_FILTER", "WRONG_AGGREGATION",
    "BUSINESS_SEMANTICS", "METRIC_DEFINITION", "TEMPORAL_REASONING", "SQL_SYNTAX",
    "EXECUTION_ERROR", "OTHER",
]
DATE_LITERAL = re.compile(r"'(\d{4}(?:-\d{2})?(?:-\d{2})?)")
AGGREGATES = (exp.Count, exp.Sum, exp.Avg, exp.Min, exp.Max)


def _parse(sql: str):
    try:
        return sqlglot.parse_one(sql, read="postgres")
    except sqlglot.errors.ParseError:
        return None


def _aggregates(tree) -> set[str]:
    out = set()
    for node in tree.find_all(*AGGREGATES):
        distinct = isinstance(node.this, exp.Distinct)
        out.add(node.key.upper() + ("_DISTINCT" if distinct else ""))
    return out


def _filter_columns(tree) -> set[str]:
    cols = set()
    for clause in list(tree.find_all(exp.Where)) + list(tree.find_all(exp.Having)):
        cols |= {c.name for c in clause.find_all(exp.Column)}
    return cols


def _years(sql: str) -> set[str]:
    return {m[:4] for m in DATE_LITERAL.findall(sql)}


def failed_semantic_checks(question: Question, sql: str) -> list:
    failed = []
    for check in question.semantic_checks:
        found = re.search(check.pattern, sql, re.IGNORECASE) is not None
        if found != (check.expect == "present"):
            failed.append(check)
    return failed


def classify(question: Question, record: dict) -> tuple[str, str]:
    """Return (failure_category, rule) for an incorrect record."""
    sql = record["generated_sql"]
    if not record["sql_valid"]:
        if record["validation_stage"] == "schema":
            return "WRONG_TABLE", "validator: unknown table"
        return "SQL_SYNTAX", f"validator: {record['validation_stage']}"
    if not record["execution_success"]:
        err = record.get("execution_error_type") or ""
        if err == "UndefinedTable":
            return "WRONG_TABLE", "postgres: UndefinedTable"
        if err == "UndefinedColumn":
            return "WRONG_COLUMN", "postgres: UndefinedColumn"
        return "EXECUTION_ERROR", f"postgres: {err or 'error'}"

    if record.get("correct_plausible") and not record.get("correct"):
        return "BUSINESS_SEMANTICS", "matched an alternative interpretation"

    for check in failed_semantic_checks(question, sql):
        category = "METRIC_DEFINITION" if check.knowledge.startswith("met.") else "BUSINESS_SEMANTICS"
        return category, f"semantic_check {check.knowledge}: /{check.pattern}/ {check.expect}"

    gen, gold = _parse(sql), _parse(question.expected_sql)
    if gen is None or gold is None:
        return "OTHER", "could not parse for comparison"

    gen_tables = {t.name for t in gen.find_all(exp.Table)}
    missing = set(question.required_tables) - gen_tables
    if missing:
        return "WRONG_TABLE", f"missing required table(s): {', '.join(sorted(missing))}"
    if "TEMPORAL" in question.tags and _years(sql) != _years(question.expected_sql):
        return "TEMPORAL_REASONING", f"date literals {sorted(_years(sql))} vs {sorted(_years(question.expected_sql))}"
    if _aggregates(gen) != _aggregates(gold):
        return "WRONG_AGGREGATION", f"aggregates {sorted(_aggregates(gen))} vs {sorted(_aggregates(gold))}"
    if _filter_columns(gen) != _filter_columns(gold):
        return "WRONG_FILTER", f"filter columns {sorted(_filter_columns(gen))} vs {sorted(_filter_columns(gold))}"
    if len(list(gen.find_all(exp.Join))) != len(list(gold.find_all(exp.Join))):
        return "WRONG_JOIN", "different number of joins"
    return "OTHER", "no rule matched"

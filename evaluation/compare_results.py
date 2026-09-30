"""Result correctness: does the generated result contain the expected answer?

Rules (in order):
  1. Scalar (expected is 1x1): the generated result must have 1 row, and any of its columns
     must equal the expected value. Column names never matter.
  2. Row counts must match.
  3. Every expected column (or those in `match_columns`) must be matched by a distinct generated
     column with the same values. Extra generated columns are allowed; column order is ignored.
  4. Rows are compared on the matched columns: as sequences if `order_matters`, else as multisets.

Values: numbers compare with rel/abs tolerance (and optionally x100 for percentages),
NULL == NULL, timestamps compare as ISO strings, `month_key` maps any date-like value to YYYY-MM.
"""

import math
import re
from dataclasses import dataclass

from evaluation.benchmark import Comparison

DATE_RE = re.compile(r"^(\d{4})-(\d{2})(?:-(\d{2}))?(?:[T ](\d{2}:\d{2}:\d{2}(?:\.\d+)?))?")


@dataclass
class CompareResult:
    correct: bool
    reason: str


def normalize(value, opts: Comparison):
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        s = value.strip()
        m = DATE_RE.match(s)
        if m:
            if opts.month_key:
                return f"{m.group(1)}-{m.group(2)}"
            s = s.replace("T", " ")
            if s.endswith(" 00:00:00"):
                s = s[: -len(" 00:00:00")]
        return s
    return value


def values_equal(a, b, opts: Comparison) -> bool:
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, float) and isinstance(b, float):
        close = lambda x, y: math.isclose(x, y, rel_tol=opts.rel_tol, abs_tol=opts.abs_tol)  # noqa: E731
        if close(a, b):
            return True
        return opts.percent_ok and (close(a * 100, b) or close(a, b * 100))
    return a == b


def _sort_key(value):
    if value is None:
        return (0, 0.0, "")
    if isinstance(value, float):
        return (1, round(value, 6), "")
    return (2, 0.0, str(value))


def _column(rows, j):
    return [r[j] for r in rows]


def _columns_match(exp_col, gen_col, opts) -> bool:
    if not opts.order_matters:
        exp_col, gen_col = sorted(exp_col, key=_sort_key), sorted(gen_col, key=_sort_key)
    return all(values_equal(a, b, opts) for a, b in zip(exp_col, gen_col))


def compare_results(expected_rows: list[list], generated_rows: list[list], opts: Comparison) -> CompareResult:
    exp = [[normalize(v, opts) for v in r] for r in expected_rows]
    gen = [[normalize(v, opts) for v in r] for r in generated_rows]

    if len(exp) == 1 and len(exp[0]) == 1:
        if len(gen) != 1:
            return CompareResult(False, f"expected 1 row, got {len(gen)}")
        ok = any(values_equal(exp[0][0], v, opts) for v in gen[0])
        return CompareResult(ok, "scalar match" if ok else f"expected {exp[0][0]!r}, got {gen[0]!r}")

    if len(exp) != len(gen):
        return CompareResult(False, f"expected {len(exp)} rows, got {len(gen)}")
    if not exp:
        return CompareResult(True, "both empty")

    wanted = opts.match_columns if opts.match_columns is not None else list(range(len(exp[0])))
    n_gen_cols = len(gen[0])
    mapping: dict[int, int] = {}
    for j in wanted:
        candidates = [g for g in range(n_gen_cols)
                      if g not in mapping.values() and _columns_match(_column(exp, j), _column(gen, g), opts)]
        if not candidates:
            return CompareResult(False, f"no generated column matches expected column {j}")
        mapping[j] = candidates[0]

    exp_rows = [[r[j] for j in wanted] for r in exp]
    gen_rows = [[r[mapping[j]] for j in wanted] for r in gen]
    if not opts.order_matters:
        exp_rows, gen_rows = sorted(exp_rows, key=lambda r: [_sort_key(v) for v in r]), \
            sorted(gen_rows, key=lambda r: [_sort_key(v) for v in r])
    for a, b in zip(exp_rows, gen_rows):
        if not all(values_equal(x, y, opts) for x, y in zip(a, b)):
            return CompareResult(False, f"row mismatch: expected {a}, got {b}")
    return CompareResult(True, "rows match" + (" (ordered)" if opts.order_matters else ""))

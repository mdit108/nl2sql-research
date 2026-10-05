"""Result correctness: does the generated result contain the expected answer?

Rules (in order):
  1. Scalar (expected is 1x1): the generated result must have 1 row, and any of its columns
     must equal the expected value. Column names never matter.
  2. Row counts must match.
  3. Every expected column (or those in `match_columns`) must be matched by a distinct generated
     column with the same multiset of values. Extra generated columns are allowed; column order is ignored.
  4. Rows are compared on the matched columns: as multisets, or, if `order_matters`, position by
     position — except that consecutive expected rows whose numeric values are all equal within
     tolerance form a "tie block" and may appear in any order inside that block
     (e.g. 4.2447 and 4.2381 are tied at abs_tol=0.01, so their order is not meaningful).

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
    """Same values regardless of order; row order is checked afterwards on whole rows."""
    exp_col, gen_col = sorted(exp_col, key=_sort_key), sorted(gen_col, key=_sort_key)
    return all(values_equal(a, b, opts) for a, b in zip(exp_col, gen_col))


def _rows_equal(a, b, opts) -> bool:
    return all(values_equal(x, y, opts) for x, y in zip(a, b))


def _tied(a, b, opts) -> bool:
    """Two expected rows are tied if they have numeric values and all of them are equal within tolerance."""
    numeric = [i for i, (x, y) in enumerate(zip(a, b)) if isinstance(x, float) and isinstance(y, float)]
    return bool(numeric) and all(values_equal(a[i], b[i], opts) for i in numeric)


def _tie_blocks(rows, opts) -> list[tuple[int, int]]:
    blocks, start = [], 0
    for i in range(1, len(rows) + 1):
        if i == len(rows) or not _tied(rows[i - 1], rows[i], opts):
            blocks.append((start, i))
            start = i
    return blocks


def _same_rows_any_order(exp_rows, gen_rows, opts) -> bool:
    unused = list(gen_rows)
    for row in exp_rows:
        match = next((g for g in unused if _rows_equal(row, g, opts)), None)
        if match is None:
            return False
        unused.remove(match)
    return True


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
    if opts.order_matters:
        for start, end in _tie_blocks(exp_rows, opts):
            if not _same_rows_any_order(exp_rows[start:end], gen_rows[start:end], opts):
                return CompareResult(False, f"row mismatch at position {start}: expected {exp_rows[start]}, "
                                            f"got {gen_rows[start]}")
        return CompareResult(True, "rows match (ordered)")

    key = lambda r: [_sort_key(v) for v in r]  # noqa: E731
    for a, b in zip(sorted(exp_rows, key=key), sorted(gen_rows, key=key)):
        if not _rows_equal(a, b, opts):
            return CompareResult(False, f"row mismatch: expected {a}, got {b}")
    return CompareResult(True, "rows match")

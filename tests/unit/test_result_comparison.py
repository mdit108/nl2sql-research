from evaluation.benchmark import Comparison
from evaluation.compare_results import compare_results

C = Comparison


def test_scalar_ignores_column_names_and_extra_columns():
    assert compare_results([[96096]], [["customers", 96096]], C()).correct
    assert not compare_results([[96096]], [[99441]], C()).correct


def test_numeric_tolerance():
    assert compare_results([[137.4189]], [[137.42]], C(abs_tol=0.01)).correct
    assert not compare_results([[137.4189]], [[137.5]], C(abs_tol=0.01)).correct


def test_percent_vs_ratio():
    assert compare_results([[0.0304]], [[3.04]], C(abs_tol=0.0005, percent_ok=True)).correct
    assert not compare_results([[0.0304]], [[3.04]], C(abs_tol=0.0005)).correct


def test_unordered_row_sets():
    exp = [["SP", 10], ["RJ", 5]]
    assert compare_results(exp, [["RJ", 5], ["SP", 10]], C()).correct


def test_ordered_rows():
    exp = [["a", 3], ["b", 2]]
    assert compare_results(exp, [["a", 3], ["b", 2]], C(order_matters=True)).correct
    assert not compare_results(exp, [["b", 2], ["a", 3]], C(order_matters=True)).correct


def test_column_order_and_extra_columns_are_ignored():
    exp = [["SP", 10], ["RJ", 5]]
    assert compare_results(exp, [[10, "SP", "x"], [5, "RJ", "y"]], C()).correct


def test_row_pairing_is_checked_not_just_columns():
    exp = [["SP", 10], ["RJ", 5]]
    # Same column multisets, wrong pairing.
    assert not compare_results(exp, [["SP", 5], ["RJ", 10]], C()).correct


def test_match_columns_only_checks_selected_columns():
    exp = [["s1", 100.0], ["s2", 90.0]]
    assert compare_results(exp, [["s1"], ["s2"]], C(order_matters=True, match_columns=[0])).correct


def test_row_count_must_match():
    assert not compare_results([["a"], ["b"]], [["a"], ["b"], ["c"]], C()).correct


def test_nulls():
    assert compare_results([[None, 1]], [[None, 1]], C()).correct
    assert not compare_results([["x", None], ["y", 1]], [["x", 0], ["y", 1]], C()).correct


def test_month_keys():
    exp = [["2018-01-01T00:00:00", 5], ["2018-02-01T00:00:00", 7]]
    gen = [["2018-01", 5], ["2018-02", 7]]
    assert compare_results(exp, gen, C(order_matters=True, month_key=True)).correct
    assert not compare_results(exp, gen, C(order_matters=True)).correct


def test_timestamp_formats():
    assert compare_results([["2018-01-01T00:00:00", 1], ["x", 2]], [["2018-01-01", 1], ["x", 2]], C()).correct

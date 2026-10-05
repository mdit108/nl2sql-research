"""Summarise one run: tables (markdown) + charts (matplotlib, default colours).

    python -m evaluation.compare                      # latest run under experiments/results/ladder
    python -m evaluation.compare --run experiments/results/ladder/<run_id>

Writes report.md and charts/*.png into the run directory.

With repeats, accuracy is the mean over all attempts; "range" is the min-max accuracy of the individual
repeats; a question is "unstable" in a condition if its repeats disagree; fixed/broken transitions use
each question's majority outcome.

Manual failure labels in <run_dir>/manual_labels.yaml override the automatic ones:
    p14/E1: {category: BUSINESS_SEMANTICS, note: "..."}      # every repeat
    p14/E1/2: {category: WRONG_FILTER, note: "..."}          # one repeat
"""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
import yaml  # noqa: E402

from app.config import PROJECT_ROOT  # noqa: E402
from evaluation.failures import CATEGORIES as FAILURE_CATEGORIES  # noqa: E402

RESULTS_DIR = PROJECT_ROOT / "experiments" / "results"
CATEGORY_ORDER = ["schema", "relational", "metric", "trap", "ambiguous"]


def load_run(run_dir: Path) -> tuple[dict, pd.DataFrame]:
    manifest = json.loads((run_dir / "manifest.json").read_text())
    df = pd.DataFrame([json.loads(line) for line in (run_dir / "records.jsonl").read_text().splitlines()])
    labels_path = run_dir / "manual_labels.yaml"
    if labels_path.exists():
        for key, label in (yaml.safe_load(labels_path.read_text()) or {}).items():
            qid, condition, *repeat = key.split("/")
            mask = (df.question_id == qid) & (df.condition == condition)
            if repeat:
                mask &= df.repeat == int(repeat[0])
            df.loc[mask, "failure_category"] = label["category"]
            df.loc[mask, "failure_rule"] = f"manual: {label.get('note', '')}"
    if "repeat" not in df:
        df["repeat"] = 0
    order = manifest["conditions"]
    df["condition"] = pd.Categorical(df["condition"], categories=order, ordered=True)
    return manifest, df.sort_values(["condition", "question_id"])


def pct(series) -> str:
    return f"{100 * series.mean():.0f}%"


def md_table(frame: pd.DataFrame) -> str:
    cols = [str(c) for c in frame.columns]
    lines = ["| " + " | ".join([frame.index.name or ""] + cols) + " |",
             "|" + "---|" * (len(cols) + 1)]
    for idx, row in frame.iterrows():
        lines.append("| " + " | ".join([str(idx)] + [str(v) for v in row.values]) + " |")
    return "\n".join(lines)


def accuracy_range(frame: pd.DataFrame) -> str:
    per_repeat = frame.groupby("repeat").correct.mean() * 100
    return f"{per_repeat.min():.0f}–{per_repeat.max():.0f}%" if len(per_repeat) > 1 else "–"


def unstable_questions(frame: pd.DataFrame) -> int:
    return int((frame.groupby("question_id").correct.nunique() > 1).sum())


def summary_table(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby("condition", observed=True)
    out = pd.DataFrame({
        "Questions": g.question_id.nunique(),
        "Attempts": g.size(),
        "Result Accuracy": g.correct.apply(pct),
        "Range across repeats": g.apply(accuracy_range, include_groups=False),
        "Unstable questions": g.apply(unstable_questions, include_groups=False),
        "Plausible (incl. alt. interpretations)": g.correct_plausible.apply(pct),
        "Execution Accuracy": g.execution_success.apply(pct),
        "SQL Valid": g.sql_valid.apply(pct),
        "Avg Input Tokens": g.input_tokens.mean().round(0).astype("Int64"),
        "Avg Output Tokens": g.output_tokens.mean().round(0).astype("Int64"),
        "Avg LLM Latency (ms)": g.llm_latency_ms.mean().round(0).astype(int),
        "Avg Total Latency (ms)": g.total_latency_ms.mean().round(0).astype(int),
        "Retrieval Recall": g.retrieval_recall.mean().round(2),
        "Retrieval Precision": g.retrieval_precision.mean().round(2),
    })
    out.index.name = "Level"
    return out.fillna("–")


def by_group(df: pd.DataFrame, column: str, order: list[str] | None = None) -> pd.DataFrame:
    frame = df.explode(column) if isinstance(df[column].iloc[0], list) else df
    table = frame.pivot_table(index="condition", columns=column, values="correct", aggfunc="mean", observed=True)
    counts = frame.groupby(column).question_id.nunique()
    if order:
        table = table[[c for c in order if c in table.columns]]
    table = (100 * table).round(0).astype(int).astype(str) + "%"
    table.columns = [f"{c} (n={counts.get(c, 0)})" for c in table.columns]
    table.index.name = "Level"
    return table


def question_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """One repeat: ✓ / ~ (alternative interpretation) / ✗. Several: correct attempts out of total."""
    def cell(frame):
        if len(frame) == 1:
            r = frame.iloc[0]
            return "✓" if r.correct else ("~" if r.correct_plausible else "✗")
        return f"{int(frame.correct.sum())}/{len(frame)}"
    m = df.groupby(["question_id", "condition"], observed=True).apply(cell, include_groups=False).unstack()
    m.index.name = "Question"
    return m


def effective_temperature(manifest: dict) -> str:
    if "effective_temperature" in manifest and manifest["effective_temperature"] is None:
        return "model default (temperature not settable)"
    return str(manifest.get("effective_temperature", manifest["temperature"]))


def comparison_pairs(conditions: list[str]) -> list[tuple[str, str]]:
    """Consecutive levels within the retrieved chain and within the gold chain, then retrieved vs gold."""
    retrieved = [c for c in conditions if "-" not in c]
    gold = [c for c in conditions if c.endswith("-gold")]
    pairs = list(zip(retrieved, retrieved[1:])) + list(zip(gold, gold[1:]))
    pairs += [(c.removesuffix("-gold"), c) for c in gold if c.removesuffix("-gold") in retrieved]
    return pairs


def transitions(df: pd.DataFrame) -> pd.DataFrame:
    """Questions fixed / broken between comparable conditions (majority outcome). Net gain hides regressions."""
    wide = df.pivot_table(index="question_id", columns="condition", values="correct", aggfunc="mean",
                          observed=True) > 0.5
    rows = []
    for a, b in comparison_pairs([str(c) for c in wide.columns]):
        fixed = wide.index[(~wide[a].astype(bool)) & wide[b].astype(bool)].tolist()
        broken = wide.index[wide[a].astype(bool) & (~wide[b].astype(bool))].tolist()
        rows.append({"Transition": f"{a} → {b}", "Fixed": len(fixed), "Broken": len(broken),
                     "Net": len(fixed) - len(broken), "Fixed questions": ", ".join(fixed) or "–",
                     "Broken questions": ", ".join(broken) or "–"})
    return pd.DataFrame(rows).set_index("Transition")


def failure_table(df: pd.DataFrame) -> pd.DataFrame:
    failed = df[~df.correct]
    t = failed.pivot_table(index="condition", columns="failure_category", values="question_id",
                           aggfunc="count", fill_value=0, observed=False)
    t = t[[c for c in FAILURE_CATEGORIES if c in t.columns]]
    t.index.name = "Level"
    return t


# ----------------------------------------------------------------------------- charts

def _style(ax, title: str, ylabel: str):
    ax.set_title(title, loc="left", fontsize=11)
    ax.set_ylabel(ylabel)
    ax.grid(axis="y", alpha=0.3, linewidth=0.8)
    ax.spines[["top", "right"]].set_visible(False)


def _series(df: pd.DataFrame, column: str, scale: float = 1.0) -> tuple[list[str], dict[str, list[float]]]:
    """Retrieved and gold conditions as two series over the same E0..En axis (gold is NaN where not run)."""
    conditions = [str(c) for c in df.condition.cat.categories]
    levels = [c for c in conditions if "-" not in c]
    means = df.groupby("condition", observed=False)[column].mean() * scale
    series = {"retrieved context": [means.get(lv, float("nan")) for lv in levels]}
    if any(c.endswith("-gold") for c in conditions):
        series["gold context"] = [means.get(f"{lv}-gold", float("nan")) for lv in levels]
    return levels, series


def _line_chart(ax, levels, series, ylim=(0, 105)):
    for label, ys in series.items():
        ax.plot(range(len(levels)), ys, marker="o", linewidth=2, markersize=6, label=label)
    ax.set_xticks(range(len(levels)), levels)
    if ylim:
        ax.set_ylim(*ylim)


def _failure_chart(ft: pd.DataFrame, out: Path) -> str:
    fig, ax = plt.subplots(figsize=(1 + 0.9 * len(ft.columns), 0.5 + 0.45 * len(ft)))
    im = ax.imshow(ft.values, aspect="auto")  # default sequential colormap
    ax.set_xticks(range(len(ft.columns)), ft.columns, rotation=40, ha="right", fontsize=8)
    ax.set_yticks(range(len(ft.index)), ft.index)
    vmax = ft.values.max() if ft.size else 0
    for i in range(ft.shape[0]):
        for j in range(ft.shape[1]):
            if ft.values[i, j]:
                ax.text(j, i, ft.values[i, j], ha="center", va="center", fontsize=8,
                        color="black" if ft.values[i, j] > vmax / 2 else "white")
    fig.colorbar(im, ax=ax, label="failed attempts")
    ax.set_title("Failure categories by level", loc="left", fontsize=11)
    return _save(fig, out / "failure_categories.png")


def charts(df: pd.DataFrame, out: Path) -> list[str]:
    out.mkdir(exist_ok=True)
    for old in out.glob("*.png"):  # never leave a chart from an earlier report behind
        old.unlink()
    files = []

    fig, ax = plt.subplots(figsize=(8, 4))
    levels, acc = _series(df, "correct", 100)
    _, exe = _series(df, "execution_success", 100)
    _line_chart(ax, levels, {f"Result accuracy, {k}": v for k, v in acc.items()}
                | {"Execution success, retrieved context": exe["retrieved context"]})
    ax.legend(frameon=False, loc="lower right", fontsize=9)
    _style(ax, "Accuracy by context level", "% of questions")
    files.append(_save(fig, out / "accuracy_by_level.png"))

    cats = [c for c in CATEGORY_ORDER if c in set(df.category)]
    fig, axes = plt.subplots(1, len(cats), figsize=(3.2 * len(cats), 3.4), sharey=True)
    for ax, cat in zip(axes, cats):
        sub = df[df.category == cat]
        levels, acc = _series(sub, "correct", 100)
        _line_chart(ax, levels, acc)
        ax.tick_params(axis="x", labelsize=8)
        _style(ax, f"{cat} (n={sub.question_id.nunique()})", "% correct" if ax is axes[0] else "")
    axes[0].legend(frameon=False, loc="upper left", fontsize=8)
    fig.suptitle("Result accuracy by question category", x=0.01, ha="left", fontsize=12)
    files.append(_save(fig, out / "accuracy_by_category.png"))

    conditions = list(df.condition.cat.categories)
    ft = failure_table(df).reindex(conditions, fill_value=0)
    if ft.size and ft.values.sum():
        files.append(_failure_chart(ft, out))

    for col, title, ylabel, fname in [
        ("total_latency_ms", "Average total latency by level", "ms", "latency.png"),
        ("input_tokens", "Average input tokens by level", "tokens", "tokens.png"),
        ("output_tokens", "Average output tokens by level (incl. reasoning)", "tokens", "output_tokens.png"),
    ]:
        fig, ax = plt.subplots(figsize=(8, 3.5))
        levels, series = _series(df, col)
        width = 0.8 / len(series)
        for k, (label, ys) in enumerate(series.items()):
            xs, hs = [], []
            for i, v in enumerate(ys):
                if pd.isna(v):
                    continue
                present = [n for n, vals in enumerate(series.values()) if not pd.isna(vals[i])]
                # Centre the bars that exist at this level (E0-E3 have no gold bar).
                xs.append(i + (present.index(k) - (len(present) - 1) / 2) * width)
                hs.append(v)
            bars = ax.bar(xs, hs, width=width * 0.92, label=label)
            ax.bar_label(bars, labels=[f"{v:,.0f}" for v in hs], fontsize=7, padding=2)
        ax.set_xticks(range(len(levels)), levels)
        ax.margins(y=0.15)
        if len(series) > 1:
            ax.legend(frameon=False, fontsize=8, loc="lower left", bbox_to_anchor=(0, 1.08), ncol=len(series))
        _style(ax, title, ylabel)
        files.append(_save(fig, out / fname))
    return files


def _save(fig, path: Path) -> str:
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path.name


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", default=None, help="run directory (default: latest ladder run)")
    args = parser.parse_args()
    if args.run:
        run_dir = PROJECT_ROOT / args.run if not Path(args.run).is_absolute() else Path(args.run)
    else:
        run_dir = sorted((RESULTS_DIR / "ladder").iterdir())[-1]
    manifest, df = load_run(run_dir)

    sections = [
        f"# Run {manifest['run_id']}",
        f"Model `{manifest['model']}` · temperature {effective_temperature(manifest)} · prompt "
        f"`{manifest['prompt_version']}` ({manifest['prompt_hash']}) · semantic layer "
        f"{manifest['semantic_layer_hash']} · embeddings `{manifest['embedding_model']}` · top-k/type "
        f"{manifest['top_k_per_type']} · benchmark {manifest['benchmark_version']} ({manifest['benchmark_hash']}) · "
        f"repeats {manifest.get('repeats', 1)} · db {manifest['database']['hash']}",
        "## Summary by level", md_table(summary_table(df)),
        "## Result accuracy by question category", md_table(by_group(df, "category", CATEGORY_ORDER)),
        "## Result accuracy by knowledge tag (a question can have several)", md_table(by_group(df, "tags")),
        "## Fixed vs broken (consecutive levels; then retrieved vs gold at the same level)", md_table(transitions(df)),
        "## Failure categories (count of failed attempts)", md_table(failure_table(df)),
        "## Per-question results (✓ correct, ~ alternative interpretation, ✗ wrong; k/n with repeats)",
        md_table(question_matrix(df)),
    ]
    files = charts(df, run_dir / "charts")
    sections += ["## Charts"] + [f"![{f}](charts/{f})" for f in files]
    report = "\n\n".join(sections) + "\n"
    (run_dir / "report.md").write_text(report)
    print(report.split("## Result accuracy by knowledge tag")[0])
    print(f"Full report: {(run_dir / 'report.md').relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()

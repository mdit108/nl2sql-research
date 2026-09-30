"""Summarise one run: tables (markdown) + charts (matplotlib, default colours).

    python -m evaluation.compare                      # latest run under experiments/results/ladder
    python -m evaluation.compare --run experiments/results/ladder/<run_id>

Writes report.md and charts/*.png into the run directory.
Manual failure labels in <run_dir>/manual_labels.yaml override the automatic ones:
    p14/E1: {category: BUSINESS_SEMANTICS, note: "..."}
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
            qid, condition = key.split("/")
            mask = (df.question_id == qid) & (df.condition == condition)
            df.loc[mask, "failure_category"] = label["category"]
            df.loc[mask, "failure_rule"] = f"manual: {label.get('note', '')}"
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


def summary_table(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby("condition", observed=True)
    out = pd.DataFrame({
        "n": g.size(),
        "Result Accuracy": g.correct.apply(pct),
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
    counts = frame[frame.condition == frame.condition.cat.categories[0]].groupby(column).size()
    if order:
        table = table[[c for c in order if c in table.columns]]
    table = (100 * table).round(0).astype(int).astype(str) + "%"
    table.columns = [f"{c} (n={counts.get(c, 0)})" for c in table.columns]
    table.index.name = "Level"
    return table


def question_matrix(df: pd.DataFrame) -> pd.DataFrame:
    symbol = df.apply(lambda r: "✓" if r.correct else ("~" if r.correct_plausible else "✗"), axis=1)
    m = df.assign(s=symbol).pivot_table(index="question_id", columns="condition", values="s",
                                        aggfunc="first", observed=True)
    m.index.name = "Question"
    return m


def transitions(df: pd.DataFrame) -> pd.DataFrame:
    """Questions fixed / broken between consecutive conditions. Net gain hides regressions."""
    wide = df.pivot_table(index="question_id", columns="condition", values="correct", aggfunc="first",
                          observed=True)
    cols = list(wide.columns)
    rows = []
    for a, b in zip(cols, cols[1:]):
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


def charts(df: pd.DataFrame, out: Path) -> list[str]:
    out.mkdir(exist_ok=True)
    conditions = list(df.condition.cat.categories)
    x = range(len(conditions))
    g = df.groupby("condition", observed=False)
    files = []

    fig, ax = plt.subplots(figsize=(8, 4))
    for col, label in [("correct", "Result accuracy"), ("execution_success", "Execution success")]:
        y = 100 * g[col].mean()
        ax.plot(x, y, marker="o", linewidth=2, markersize=6, label=label)
        ax.annotate(label, (len(conditions) - 1, y.iloc[-1]), xytext=(6, 0), textcoords="offset points",
                    va="center", fontsize=9)
    ax.set_xticks(list(x), conditions)
    ax.set_ylim(0, 105)
    ax.legend(frameon=False, loc="upper left")
    _style(ax, "Accuracy by context level", "% of questions")
    files.append(_save(fig, out / "accuracy_by_level.png"))

    cats = [c for c in CATEGORY_ORDER if c in set(df.category)]
    fig, axes = plt.subplots(1, len(cats), figsize=(3 * len(cats), 3.2), sharey=True)
    for ax, cat in zip(axes, cats):
        sub = df[df.category == cat].groupby("condition", observed=False).correct.mean() * 100
        ax.plot(x, sub, marker="o", linewidth=2, markersize=5)
        n = (df[(df.category == cat)].condition == conditions[0]).sum()
        ax.set_xticks(list(x), conditions, fontsize=7, rotation=90)
        ax.set_ylim(0, 105)
        _style(ax, f"{cat} (n={n})", "% correct" if ax is axes[0] else "")
    fig.suptitle("Result accuracy by question category", x=0.01, ha="left", fontsize=12)
    files.append(_save(fig, out / "accuracy_by_category.png"))

    ft = failure_table(df).reindex(conditions, fill_value=0)
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
    fig.colorbar(im, ax=ax, label="failed questions")
    ax.set_title("Failure categories by level", loc="left", fontsize=11)
    files.append(_save(fig, out / "failure_categories.png"))

    for col, title, ylabel, fname in [
        ("total_latency_ms", "Average total latency by level", "ms", "latency.png"),
        ("input_tokens", "Average input tokens by level", "tokens", "tokens.png"),
    ]:
        fig, ax = plt.subplots(figsize=(8, 3.5))
        y = g[col].mean()
        bars = ax.bar(list(x), y, width=0.6)
        ax.bar_label(bars, labels=[f"{v:,.0f}" for v in y], fontsize=8, padding=2)
        ax.set_xticks(list(x), conditions)
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
        f"Model `{manifest['model']}` · temperature {manifest['temperature']} · prompt "
        f"`{manifest['prompt_version']}` ({manifest['prompt_hash']}) · semantic layer "
        f"{manifest['semantic_layer_hash']} · embeddings `{manifest['embedding_model']}` · top-k/type "
        f"{manifest['top_k_per_type']} · benchmark {manifest['benchmark_version']} ({manifest['benchmark_hash']}) · "
        f"db {manifest['database']['hash']}",
        "## Summary by level", md_table(summary_table(df)),
        "## Result accuracy by question category", md_table(by_group(df, "category", CATEGORY_ORDER)),
        "## Result accuracy by knowledge tag (a question can have several)", md_table(by_group(df, "tags")),
        "## Fixed vs broken between consecutive levels", md_table(transitions(df)),
        "## Failure categories (count of failed questions)", md_table(failure_table(df)),
        "## Per-question results (✓ correct, ~ alternative interpretation, ✗ wrong)",
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

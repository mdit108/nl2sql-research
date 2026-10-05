"""Run the benchmark across context levels.

    python -m evaluation.run                                # E0..E6, retrieved context, 3 repeats, LLM from .env
    python -m evaluation.run --conditions E3,E4,E4-gold    # "-gold" = the question's required knowledge items
    python -m evaluation.run --repeats 1 --questions p10   # quick check
    python -m evaluation.run --llm gold-sql --repeats 1    # self-test: mock LLM returns the gold SQL

Writes experiments/results/<name>/<run_id>/{manifest.json, records.jsonl, traces.jsonl}.
Generation (the pipeline) and evaluation (compare/classify) are separate steps inside `evaluate()`.
"""

import argparse
import json
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from app.config import PROJECT_ROOT, get_settings
from app.database.fingerprint import database_fingerprint
from app.llm import MockProvider, get_llm
from app.nl2sql.context import get_level
from app.nl2sql.pipeline import NL2SQLPipeline, Trace
from app.retrieval.knowledge import (KnowledgeRetriever, load_knowledge_items, semantic_layer_hash,
                                     stale_knowledge_items)
from evaluation.benchmark import BENCHMARK_DIR, Question, load_benchmark, load_expected
from evaluation.compare_results import compare_results
from evaluation.failures import classify, failed_semantic_checks

RESULTS_DIR = PROJECT_ROOT / "experiments" / "results"
DEFAULT_CONDITIONS = "E0,E1,E2,E3,E4,E5,E6"
KNOWLEDGE_TYPES = {i.id: i.knowledge_type for i in load_knowledge_items()}


def parse_condition(condition: str) -> tuple[str, str]:
    level, _, mode = condition.partition("-")
    get_level(level)  # validates
    return level, mode or "retrieved"


def retrieval_scores(question: Question, level: str, trace: Trace) -> dict:
    """Retrieval quality, restricted to the knowledge types this level allows.

    recall    = required items retrieved / required items
    precision = relevant items retrieved / items retrieved   (relevant = required + related)
    """
    allowed = set(get_level(level).knowledge_types)
    if not allowed:
        return {"retrieval_precision": None, "retrieval_recall": None, "required_knowledge_at_level": [],
                "missed_knowledge": []}
    required = {k for k in question.required_knowledge if KNOWLEDGE_TYPES.get(k) in allowed}
    relevant = required | {k for k in question.related_knowledge if KNOWLEDGE_TYPES.get(k) in allowed}
    retrieved = {i.id for i in trace.retrieved}
    return {
        "retrieval_precision": round(len(relevant & retrieved) / len(retrieved), 3) if retrieved else None,
        "retrieval_recall": round(len(required & retrieved) / len(required), 3) if required else None,
        "required_knowledge_at_level": sorted(required),
        "missed_knowledge": sorted(required - retrieved),
    }


def evaluate(question: Question, trace: Trace) -> dict:
    expected = load_expected(question.id)
    record = {
        "question_id": question.id, "category": question.category, "tags": question.tags,
        "difficulty": question.difficulty,
        **trace.model_dump(exclude={"prompt", "llm_output", "rows", "question"}),
        "rows_preview": trace.rows[:10],
    }
    correct, plausible, reason = False, False, None
    if trace.execution_success:
        result = compare_results(expected["rows"], trace.rows, question.comparison)
        correct, reason = result.correct, result.reason
        plausible = correct or any(
            compare_results(alt_gt["rows"], trace.rows, alt.comparison).correct
            for alt, alt_gt in zip(question.alternatives, expected["alternatives"]))
    record.update(correct=correct, correct_plausible=plausible, compare_reason=reason)
    record["semantic_checks_failed"] = [c.knowledge for c in failed_semantic_checks(question, trace.generated_sql)]
    record.update(retrieval_scores(question, trace.level, trace))
    if correct:
        record.update(failure_category=None, failure_rule=None)
    else:
        record["failure_category"], record["failure_rule"] = classify(question, record)
    return record


def git_commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=PROJECT_ROOT, capture_output=True,
                              text=True, check=True).stdout.strip() or None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark", default=str(BENCHMARK_DIR / "pilot.yaml"))
    parser.add_argument("--conditions", default=DEFAULT_CONDITIONS)
    parser.add_argument("--top-k", type=int, default=None, help="items per knowledge type (default RETRIEVAL_TOP_K)")
    parser.add_argument("--questions", default=None, help="comma-separated ids to run (default all)")
    parser.add_argument("--name", default="ladder", help="experiment name (results subdirectory)")
    parser.add_argument("--llm", choices=["env", "gold-sql", "mock"], default="env")
    parser.add_argument("--repeats", type=int, default=3,
                        help="runs per question x condition (the model may not support temperature 0)")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    settings = get_settings()
    top_k = args.top_k or settings.retrieval_top_k
    bench = load_benchmark(args.benchmark)
    questions = bench.questions
    if args.questions:
        wanted = set(args.questions.split(","))
        questions = [q for q in questions if q.id in wanted]
    conditions = [parse_condition(c) for c in args.conditions.split(",")]

    if args.llm == "gold-sql":
        llm = MockProvider({q.question.strip(): q.expected_sql for q in questions})
        llm.model = "gold-sql-mock"
    elif args.llm == "mock":
        llm = MockProvider()
    else:
        llm = get_llm(settings)
    pipeline = NL2SQLPipeline(llm, KnowledgeRetriever())

    fingerprint = database_fingerprint()
    if stale := stale_knowledge_items(pipeline.retriever.embedder.model):
        raise SystemExit(f"Knowledge store is out of date with semantic/*.yaml ({', '.join(stale)}); "
                         "run `python scripts/index_knowledge.py`")
    for q in questions:
        if load_expected(q.id)["db_fingerprint"] != fingerprint["hash"]:
            raise SystemExit(f"{q.id}: ground truth was computed on different data; rerun evaluation.ground_truth")

    started = datetime.now(timezone.utc)
    run_id = started.strftime("%Y%m%dT%H%M%SZ")
    out_dir = RESULTS_DIR / args.name / run_id
    out_dir.mkdir(parents=True)
    manifest = {
        "run_id": run_id, "timestamp": started.isoformat(timespec="seconds"), "experiment": args.name,
        "conditions": [f"{lv}-{m}" if m != "retrieved" else lv for lv, m in conditions],
        "model": llm.model, "llm_provider": args.llm if args.llm != "env" else settings.llm_provider,
        "temperature": settings.llm_temperature, "max_tokens": settings.llm_max_tokens,  # requested values
        "prompt_version": pipeline.prompt.version, "prompt_hash": pipeline.prompt.hash,
        "embedding_provider": settings.embedding_provider, "embedding_model": settings.embedding_model,
        "top_k_per_type": top_k, "semantic_layer_hash": semantic_layer_hash(),
        "benchmark": bench.path, "benchmark_version": bench.version, "benchmark_hash": bench.hash,
        "question_ids": [q.id for q in questions], "repeats": args.repeats,
        "database": fingerprint, "git_commit": git_commit(),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))

    jobs = [(q, level, mode, r) for level, mode in conditions for q in questions for r in range(args.repeats)]

    def work(job):
        q, level, mode, repeat = job
        trace = pipeline.run(q.question, level, mode, top_k, gold_ids=q.required_knowledge)
        record = evaluate(q, trace)
        record["condition"] = level if mode == "retrieved" else f"{level}-{mode}"
        record["repeat"] = repeat
        record["run_id"] = run_id
        return trace, record

    start = time.perf_counter()
    with ThreadPoolExecutor(args.workers) as pool, \
            open(out_dir / "records.jsonl", "w") as rec_f, open(out_dir / "traces.jsonl", "w") as tr_f:
        for i, (trace, record) in enumerate(pool.map(work, jobs), 1):
            rec_f.write(json.dumps(record) + "\n")
            tr_f.write(trace.model_dump_json() + "\n")
            mark = "ok " if record["correct"] else ("~  " if record["correct_plausible"] else "X  ")
            print(f"[{i:>4}/{len(jobs)}] {record['condition']:10s} {record['question_id']} r{record['repeat']} {mark}"
                  f"{record['failure_category'] or ''}")
    # Some models reject temperature; the provider then drops it. Record what was actually sent.
    manifest["effective_temperature"] = getattr(llm, "temperature", settings.llm_temperature)
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"Done in {time.perf_counter() - start:.0f}s -> {out_dir}")
    print(f"Next: python -m evaluation.compare --run {out_dir.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()

"""Ask one question at one context level and see everything the pipeline did.

    python scripts/ask.py "How many customers are there?"
    python scripts/ask.py "Who are our best customers?" --level E3
    python scripts/ask.py "What is the average order value?" --level E6 --show-prompt
    python scripts/ask.py "..." --level E5 --gold met.average_order_value,met.revenue
"""

import argparse

from app.config import get_settings
from app.llm import get_llm
from app.nl2sql.pipeline import NL2SQLPipeline


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("question")
    parser.add_argument("--level", default="E6", help="E0..E6 (default E6)")
    parser.add_argument("--top-k", type=int, default=None)
    parser.add_argument("--gold", default=None, help="comma-separated knowledge ids to use instead of retrieval")
    parser.add_argument("--show-prompt", action="store_true")
    parser.add_argument("--rows", type=int, default=20, help="result rows to print")
    args = parser.parse_args()

    pipeline = NL2SQLPipeline(get_llm())
    mode = "gold" if args.gold else "retrieved"
    t = pipeline.run(args.question, args.level, mode, args.top_k or get_settings().retrieval_top_k,
                     args.gold.split(",") if args.gold else None)

    if args.show_prompt:
        print("=" * 30, "PROMPT", "=" * 30)
        print(t.prompt)
    if t.retrieved:
        print("=" * 30, f"CONTEXT ({t.context_mode})", "=" * 30)
        for i in t.retrieved:
            sim = f"{i.similarity:.2f}" if i.similarity is not None else "gold"
            print(f"  {sim:>5}  {i.knowledge_type:16s} {i.id}")
    print("=" * 30, "SQL", "=" * 30)
    print(t.generated_sql)
    print("=" * 30, "RESULT", "=" * 30)
    if not t.sql_valid:
        print(f"Rejected by validator ({t.validation_stage}): {t.validation_error}")
    elif not t.execution_success:
        print(f"Database error ({t.execution_error_type}): {t.execution_error}")
    else:
        print(" | ".join(t.columns))
        for row in t.rows[: args.rows]:
            print(" | ".join(str(v) for v in row))
        if t.row_count > args.rows:
            print(f"... {t.row_count - args.rows} more rows")
    print("=" * 30, "STATS", "=" * 30)
    print(f"model={t.model} level={t.level} input_tokens={t.input_tokens} output_tokens={t.output_tokens} "
          f"reasoning_tokens={t.reasoning_tokens} llm={t.llm_latency_ms:.0f}ms "
          f"retrieval={t.retrieval_latency_ms:.0f}ms execution={t.execution_latency_ms:.0f}ms "
          f"total={t.total_latency_ms:.0f}ms")


if __name__ == "__main__":
    main()

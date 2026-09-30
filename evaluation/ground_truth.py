"""Compute ground-truth results by running each question's trusted SQL.

    python -m evaluation.ground_truth [--benchmark benchmark/pilot.yaml]

Writes benchmark/expected/<id>.json (and alternatives) with the database fingerprint,
so a result is only trusted against the same data it was computed on.
"""

import argparse
import json

from sqlalchemy import text

from app.database import readonly_engine
from app.database.fingerprint import database_fingerprint
from app.nl2sql.sql import to_jsonable
from evaluation.benchmark import BENCHMARK_DIR, EXPECTED_DIR, load_benchmark


def run_sql(sql: str) -> dict:
    with readonly_engine().connect() as conn:
        result = conn.execute(text(sql))
        return {"columns": list(result.keys()), "rows": [[to_jsonable(v) for v in r] for r in result]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark", default=str(BENCHMARK_DIR / "pilot.yaml"))
    args = parser.parse_args()

    bench = load_benchmark(args.benchmark)
    fingerprint = database_fingerprint()["hash"]
    EXPECTED_DIR.mkdir(parents=True, exist_ok=True)
    for q in bench.questions:
        gt = run_sql(q.expected_sql)
        gt["alternatives"] = [run_sql(a.sql) for a in q.alternatives]
        gt["db_fingerprint"] = fingerprint
        gt["benchmark_version"] = bench.version
        (EXPECTED_DIR / f"{q.id}.json").write_text(json.dumps(gt, indent=1))
        preview = gt["rows"][0] if len(gt["rows"]) == 1 else f"{len(gt['rows'])} rows"
        print(f"  {q.id}: {preview}")
        if not gt["rows"]:
            print(f"  WARNING {q.id}: empty ground truth")
    print(f"Wrote {len(bench.questions)} ground-truth files (db {fingerprint})")


if __name__ == "__main__":
    main()

# NL2SQL Research Platform — *What does an NL2SQL model actually need to know?*

A small, inspectable platform for measuring which kinds of context make NL2SQL reliable —
and where more context stops helping. One pipeline; only the context changes (the **Context Ladder**):

| Level | Adds | Source |
|---|---|---|
| E0 | question only | — |
| E1 | tables, columns, types | PostgreSQL catalog |
| E2 | primary/foreign keys, relationships, cardinality | catalog + `semantic/relationships.yaml` |
| E3 | table and column descriptions | `semantic/descriptions.yaml` |
| E4 | business entity definitions | pgvector top-k from `semantic/entities.yaml` |
| E5 | metric definitions | pgvector top-k from `semantic/metrics.yaml` |
| E6 | domain rules and known pitfalls | pgvector top-k from `semantic/domain_rules.yaml` |
| E7 | worked examples | *not built yet* |
| E8 | validation + one correction | *not built yet* |

Any level from E4 up can also run in **gold** mode (`E5-gold`). In gold mode the benchmark's hand-picked knowledge
items replace retrieval, which separates *retrieval failures* from *reasoning failures*.

## How it works

```
question ─► context builder ─► prompt (prompts/generation/v1.md) ─► LLM ─► extract SQL
             │  schema: rendered from the catalog (E1–E3, always the full schema)
             │  knowledge: embed question → pgvector cosine top-k per type (E4–E6)
             ▼
         validate (sqlglot: one SELECT/WITH, no DML/DDL, known tables)
             ▼
         execute (read-only role + READ ONLY transaction + timeout) ─► trace
             ▼
         evaluate (result comparison vs ground truth, retrieval precision/recall, failure category)
```

| Component | File |
|---|---|
| Context levels | `app/nl2sql/context.py` |
| Schema rendering | `app/nl2sql/schema.py` |
| Semantic retrieval | `app/retrieval/knowledge.py` (`search()` is the whole algorithm) |
| Embeddings | `app/retrieval/embeddings.py` |
| Prompt | `prompts/generation/v1.md` + `app/nl2sql/prompt.py` |
| LLM providers | `app/llm/__init__.py` (OpenAI-compatible, mock) |
| SQL validation and execution | `app/nl2sql/sql.py` |
| Pipeline and trace | `app/nl2sql/pipeline.py` |
| Result comparison | `evaluation/compare_results.py` |
| Failure classification | `evaluation/failures.py` |
| Runner and report | `evaluation/run.py`, `evaluation/compare.py` |

## Setup (no Docker)

### 1. PostgreSQL 17 + pgvector

**macOS (Homebrew)**
```bash
brew install postgresql@17 pgvector
brew services start postgresql@17
export PATH="/opt/homebrew/opt/postgresql@17/bin:$PATH"
```

**Ubuntu/Debian**
```bash
sudo apt install postgresql-17 postgresql-17-pgvector    # PGDG repository
sudo -u postgres createuser --superuser "$USER"
```

**Windows:** install PostgreSQL 17 with the EDB installer, then install pgvector
([instructions](https://github.com/pgvector/pgvector#windows)). Run the `psql` commands below from the
"SQL Shell", or add PostgreSQL's `bin` to `PATH`.

### 2. Database, roles, extension

```bash
psql -d postgres -f scripts/init_db.sql
```

This creates two roles and the database:
- `nl2sql_owner` owns the database, runs migrations and loads data.
- `nl2sql_readonly` executes generated SQL. It has SELECT on `olist` only, runs read-only transactions, and has a 15 s timeout.

It also creates the `nl2sql_research` database and the `vector` extension. The roles are passwordless for local
trust auth. If your server requires passwords, see the comment at the top of the script.

### 3. Python environment

```bash
python3.12 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env               # Windows: copy .env.example .env
```

Then edit `.env`. You need to set `LLM_BASE_URL`, `LLM_API_KEY` and `LLM_MODEL` before any real run. **Never commit `.env`.**

### 4. Schema, data, knowledge store, ground truth

```bash
alembic upgrade head
python scripts/download_data.py
python scripts/load_data.py
python scripts/validate_data.py       # writes data/reports/data_quality.md
python scripts/index_knowledge.py     # embeds semantic/*.yaml into pgvector
python -m evaluation.ground_truth     # runs the trusted SQL, writes benchmark/expected/*.json
pytest
```

The `Makefile` wraps these steps: `make setup`, then `make test`.

## Running experiments

```bash
python scripts/check_providers.py                  # is the LLM reachable?
python -m evaluation.run --llm gold-sql --name selftest # gold SQL must score 100% (checks the evaluator)
python -m evaluation.run                           # E0..E6 on the pilot
python -m evaluation.run --conditions E4-gold,E5-gold,E6-gold
python -m evaluation.compare                       # report.md + charts/ in the run directory
```

Each run writes to `experiments/results/<name>/<run_id>/`:
- `manifest.json`: model, temperature, prompt version and hash, semantic-layer hash, embedding model, top-k, benchmark hash, database fingerprint, PostgreSQL version and git commit.
- `records.jsonl`: one evaluated record per question × condition.
- `traces.jsonl`: the full prompt, raw LLM output and result rows.

To correct a failure label after manual inspection, add it to `<run_dir>/manual_labels.yaml`:
```yaml
p14/E1: {category: BUSINESS_SEMANTICS, note: counted customer_id}
```

## API

```bash
uvicorn app.api.main:app --reload
curl -s localhost:8000/api/v1/query -H 'content-type: application/json' \
  -d '{"question": "How many customers are there?", "level": "E4"}'
```
Endpoints: `POST /api/v1/query`, `GET /api/v1/schema`, `GET /api/v1/metrics`, `GET /api/v1/health`.

## Configuration

Everything is read from `.env`; see `.env.example`.
- The LLM can be any OpenAI-compatible `/chat/completions` endpoint (a hosted API, or a local server such as vLLM or Ollama). `LLM_PROVIDER=mock` needs no key.
- Embeddings default to a local model (`fastembed`, `BAAI/bge-small-en-v1.5`), so retrieval is free, offline and deterministic. `EMBEDDING_PROVIDER=openai_compatible` switches to an API endpoint.

## Dataset

Olist Brazilian E-Commerce, CC BY-NC-SA 4.0. See [`data/README.md`](data/README.md). The data is not redistributed here.

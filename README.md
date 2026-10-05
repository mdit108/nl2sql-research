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

Any level from E4 up can also run in **gold** mode (`E5-gold`). Gold mode replaces retrieval with each question's
`required_knowledge` items (the minimal set it needs), which separates *retrieval failures* from *reasoning failures*.

Findings so far: [`docs/pilot-review.md`](docs/pilot-review.md). Research design: [`docs/research-notes.md`](docs/research-notes.md).

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
| Benchmark | `benchmark/pilot.yaml` (26 questions) + `benchmark/expected/*.json` (ground truth) |
| Semantic layer | `semantic/*.yaml` (descriptions, relationships, entities, metrics, domain rules) |

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

## Asking a single question

```bash
python scripts/ask.py "How many customers are there?" --level E3
python scripts/ask.py "What is the average order value?" --level E6 --show-prompt
python scripts/ask.py "What is the average order value?" --level E6 --gold met.average_order_value
```

Prints the retrieved knowledge (with similarities), the generated SQL, the result, tokens and latency.
Knowledge ids are the `id:` fields in `semantic/entities.yaml`, `metrics.yaml` and `domain_rules.yaml`.

## Running experiments

```bash
python scripts/check_providers.py                          # is the LLM reachable?
python -m evaluation.run --llm gold-sql --repeats 1        # self-test: gold SQL must score 100%
make pilot                                                 # E0..E6 + E4..E6 gold, 3 repeats, then the report
python -m evaluation.run --conditions E3,E5 --questions p10,p11 --repeats 1   # a quick slice
python -m evaluation.compare --run experiments/results/ladder/<run_id>
```

- **Repeats** (default 3): some models (including the one used for the pilot) only run at their default
  temperature, so each question × condition is run several times. The report shows mean accuracy, the range
  across repeats, and how many questions were unstable.
- **Guards**: the runner refuses to start if the ground truth was computed on different data, or if
  `semantic/*.yaml` changed since the last `python scripts/index_knowledge.py`.

Each run writes to `experiments/results/<name>/<run_id>/` (git-ignored):
- `manifest.json`: model, requested and effective temperature, prompt version and hash, semantic-layer hash, embedding model, top-k, repeats, benchmark version and hash, database fingerprint, PostgreSQL version, git commit.
- `records.jsonl`: one evaluated record per question × condition × repeat.
- `traces.jsonl`: the full prompt, raw LLM output and result rows.
- `report.md` and `charts/`: written by `evaluation.compare`.

To correct a failure label after manual inspection, add it to `<run_dir>/manual_labels.yaml`
and re-run `evaluation.compare`:
```yaml
p14/E1: {category: BUSINESS_SEMANTICS, note: counted customer_id}     # all repeats
p15/E5/2: {category: OTHER, note: rounding}                           # one repeat
```

## Editing the semantic layer or benchmark

- After editing `semantic/*.yaml`, run `python scripts/index_knowledge.py`.
- Every knowledge item must be **self-contained**: it is retrieved on its own, so it must not rely on a term
  that only another item defines. `tests/unit/test_metric_definitions.py` checks this for metrics.
- After editing `benchmark/pilot.yaml`, run `python -m evaluation.ground_truth`.

## API

```bash
uvicorn app.api.main:app --reload
curl -s localhost:8000/api/v1/query -H 'content-type: application/json' \
  -d '{"question": "How many customers are there?", "level": "E4"}'
```
Endpoints: `POST /api/v1/query`, `GET /api/v1/schema`, `GET /api/v1/metrics`, `GET /api/v1/health`.
Interactive docs at `http://localhost:8000/docs`.

`POST /api/v1/query` fields:
- `question`
- `level`: `E0`–`E6`, default `E6`
- `context_mode`: `retrieved` (default) or `gold`
- `top_k`: items retrieved per knowledge type; default `RETRIEVAL_TOP_K`
- `knowledge_ids`: the items to use in `gold` mode

The response is the full trace: retrieved items and similarities, prompt, SQL, result rows, tokens and latencies.

## Configuration

Everything is read from `.env`; see `.env.example`.
- The LLM can be any OpenAI-compatible `/chat/completions` endpoint (a hosted API, or a local server such as vLLM or Ollama). `LLM_PROVIDER=mock` needs no key.
- `LLM_TEMPERATURE` is sent if the model accepts it; if the model rejects it, the request is retried without it and the manifest records `effective_temperature: null`.
- Embeddings default to a local model (`fastembed`, `BAAI/bge-small-en-v1.5`), so retrieval is free, offline and deterministic. `EMBEDDING_PROVIDER=openai_compatible` switches to an API endpoint.

## Dataset

Olist Brazilian E-Commerce, CC BY-NC-SA 4.0. See [`data/README.md`](data/README.md). The data is not redistributed here.

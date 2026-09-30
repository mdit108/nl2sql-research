# Research notes

## Research question

What types of context actually improve NL2SQL reliability, and where does additional context stop
helping or start hurting?

## Hypothesis (to be tested, not assumed)

Reliable NL2SQL depends more on business semantics (identity, metric definitions, domain rules)
than on schema detail. The experiments are designed so the opposite results are also visible:
- schema is enough
- returns diminish
- more context hurts (dilution)
- some context helps one question type and hurts another

## Dataset

Olist Brazilian E-Commerce (CC BY-NC-SA 4.0), loaded into a normalised PostgreSQL schema.
See `data/README.md` and `data/reports/data_quality.md`.

## Benchmark design

Pilot: 20 questions in `benchmark/pilot.yaml`:

| Category | Questions |
|---|---:|
| schema | 4 |
| relational | 4 |
| metric | 5 |
| trap | 4 |
| ambiguous | 3 |

- Each question has trusted SQL whose *result* is the ground truth, the tables it requires, and the knowledge items it depends on.
- Includes **control** questions (answerable from schema alone) and **anti-trap** questions (p03, p17), where a semantic rule must *not* be applied.
- Ambiguous questions have one "organisation" interpretation (the one in the semantic layer) plus documented reasonable alternatives.

## Experimental variables

- **Independent:** context level (E0–E6); context mode (retrieved vs gold).
- **Held constant:** model, temperature (0), prompt template, embedding model, top-k per type (3), benchmark version, database fingerprint.

## Experimental configurations

The Context Ladder (see README). Gold conditions E4–E6 separate retrieval quality from the value of the knowledge itself.

## Evaluation metrics

- **Primary:** result correctness. See `evaluation/compare_results.py` for scalar, set, ordered, tolerance and NULL rules.
- **Secondary:**
  - "plausible" correctness, which also accepts alternative interpretations
  - execution success
  - SQL validity
  - input and output tokens
  - latency
  - retrieval precision and recall against required knowledge
  - rule-based failure category

## Potential confounders

- **Prompt length grows with level.** Gains may come from the kind of context or just the amount. The planned context-quantity experiment addresses this.
- **Pretraining contamination.** Olist is a widely used public dataset, so the model may already know its quirks. E0 accuracy partly measures this.
- **Authoring bias.** The same author wrote the semantic layer and the benchmark. This favours E4–E6, especially on ambiguous questions, where "correct" means "matches our definition".
- **Model non-determinism**, even at temperature 0. The pilot runs once.
- **Small n.** 20 questions, and 3–5 per category. Pilot differences are directional only.

## Results

*Populated only from actual runs. See `experiments/results/<name>/<run_id>/report.md`.*

## Failure analysis

*Populated from manual inspection of pilot failures.*

## Observations

## Open questions
